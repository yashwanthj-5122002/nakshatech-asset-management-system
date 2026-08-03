import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useSearchParams } from 'react-router-dom'

const STORAGE_KEY = 'nakshatech_it_reporting_month'
const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/

export function currentMonthKey(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function validMonth(value: string | null | undefined): value is string {
  return Boolean(value && MONTH_PATTERN.test(value))
}

type ITMonthContextValue = {
  selectedMonth: string
  presentMonth: string
  isPresentMonth: boolean
  setSelectedMonth: (month: string) => void
  returnToPresent: () => void
}

const ITMonthContext = createContext<ITMonthContextValue | null>(null)

export function ITMonthProvider({ children }: { children: ReactNode }) {
  const presentMonth = currentMonthKey()
  const [selectedMonth, setSelectedMonthState] = useState(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    return validMonth(saved) ? saved : presentMonth
  })

  const setSelectedMonth = useCallback((month: string) => {
    if (validMonth(month)) setSelectedMonthState(month)
  }, [])

  const returnToPresent = useCallback(() => {
    setSelectedMonthState(presentMonth)
  }, [presentMonth])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, selectedMonth)
  }, [selectedMonth])

  const value = useMemo<ITMonthContextValue>(() => ({
    selectedMonth,
    presentMonth,
    isPresentMonth: selectedMonth === presentMonth,
    setSelectedMonth,
    returnToPresent,
  }), [presentMonth, returnToPresent, selectedMonth, setSelectedMonth])

  return <ITMonthContext.Provider value={value}>{children}</ITMonthContext.Provider>
}

export function useITMonth(): ITMonthContextValue {
  const context = useContext(ITMonthContext)
  if (!context) throw new Error('useITMonth must be used inside ITMonthProvider')
  return context
}

/**
 * Keeps the global IT reporting month and the current page's ?month= query
 * synchronized without allowing the previous URL value to overwrite a month
 * that the user has just selected.
 *
 * The previous implementation watched both values and immediately copied a
 * valid URL month back into context. During a user change React rendered the
 * new context value before React Router committed the new query string, so the
 * still-old URL (usually the present month) won and reset the selection.
 */
export function useITMonthUrl(): ITMonthContextValue {
  const monthContext = useITMonth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlMonth = searchParams.get('month')
  const pendingMonthRef = useRef<string | null>(null)

  const writeMonthToUrl = useCallback((month: string) => {
    if (!validMonth(month)) return
    const next = new URLSearchParams(searchParams)
    next.set('month', month)
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const setSelectedMonth = useCallback((month: string) => {
    if (!validMonth(month)) return

    // Mark this as a deliberate local change before either React state or the
    // Router query string can render independently. This prevents the old URL
    // value from winning during the transition.
    pendingMonthRef.current = month
    monthContext.setSelectedMonth(month)
    writeMonthToUrl(month)
  }, [monthContext, writeMonthToUrl])

  const returnToPresent = useCallback(() => {
    setSelectedMonth(monthContext.presentMonth)
  }, [monthContext.presentMonth, setSelectedMonth])

  useEffect(() => {
    if (validMonth(urlMonth)) {
      const pendingMonth = pendingMonthRef.current

      if (pendingMonth) {
        if (urlMonth === pendingMonth) {
          // Router has committed the user's selected month.
          pendingMonthRef.current = null
        } else {
          // The URL is temporarily stale while React Router applies the local
          // selection. Never copy this stale value back into global state.
          return
        }
      }

      // A direct URL, browser Back/Forward action, or sidebar navigation is
      // authoritative once no local month transition is pending.
      if (urlMonth !== monthContext.selectedMonth) {
        monthContext.setSelectedMonth(urlMonth)
      }
      return
    }

    // Pages opened without a month inherit the last selected IT month.
    writeMonthToUrl(monthContext.selectedMonth)
  }, [monthContext, urlMonth, writeMonthToUrl])

  const selectedMonth = pendingMonthRef.current
    ?? (validMonth(urlMonth) ? urlMonth : monthContext.selectedMonth)

  return useMemo<ITMonthContextValue>(() => ({
    selectedMonth,
    presentMonth: monthContext.presentMonth,
    isPresentMonth: selectedMonth === monthContext.presentMonth,
    setSelectedMonth,
    returnToPresent,
  }), [monthContext.presentMonth, returnToPresent, selectedMonth, setSelectedMonth])
}

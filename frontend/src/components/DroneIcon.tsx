import type { ElementType, SVGProps } from 'react'

export type AppIconProps = SVGProps<SVGSVGElement> & {
  size?: number | string
  strokeWidth?: number | string
}

export type AppIcon = ElementType

export function DroneIcon({ size = 24, strokeWidth = 2, ...props }: AppIconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M9 10h6l1.6 2.4a2 2 0 0 1 .34 1.12V16H7v-2.48a2 2 0 0 1 .34-1.12L9 10Z" />
      <path d="M10 16v2h4v-2" />
      <path d="M8 11 4.5 8.5M16 11l3.5-2.5" />
      <path d="M3 7h4M17 7h4" />
      <path d="M5 7v2M19 7v2" />
      <path d="M9.5 13h5" />
      <circle cx="12" cy="14" r="1" />
    </svg>
  )
}

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import { ITMonthProvider } from './context/ITMonthContext'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ITMonthProvider>
          <App />
        </ITMonthProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)

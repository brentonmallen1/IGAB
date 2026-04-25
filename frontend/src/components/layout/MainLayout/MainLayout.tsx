import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from '../Sidebar/Sidebar'
import { Header } from '../Header/Header'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import './MainLayout.css'

export function MainLayout() {
  const theme = useAppStore((s) => s.theme)
  const mobileSidebarOpen = useUIStore((s) => s.mobileSidebarOpen)
  const setMobileSidebarOpen = useUIStore((s) => s.setMobileSidebarOpen)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  return (
    <div className="main-layout">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      {mobileSidebarOpen && (
        <div
          className="main-layout__backdrop"
          onClick={() => setMobileSidebarOpen(false)}
          onKeyDown={(e) => e.key === 'Enter' || e.key === ' ' ? setMobileSidebarOpen(false) : undefined}
          role="button"
          tabIndex={0}
          aria-label="Close sidebar"
        />
      )}
      <Sidebar />
      <div className="main-layout__content">
        <Header />
        <main id="main-content" className="main-layout__main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

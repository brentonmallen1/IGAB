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
      {mobileSidebarOpen && (
        <div className="main-layout__backdrop" onClick={() => setMobileSidebarOpen(false)} />
      )}
      <Sidebar />
      <div className="main-layout__content">
        <Header />
        <main className="main-layout__main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

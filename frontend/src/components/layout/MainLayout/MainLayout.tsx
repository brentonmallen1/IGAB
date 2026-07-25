import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from '../Sidebar/Sidebar'
import { Header } from '../Header/Header'
import { BottomNav } from '../BottomNav/BottomNav'
import { MoreSheet } from '../MoreSheet/MoreSheet'
import { QuickAddSheet } from '../../transactions/QuickAddSheet/QuickAddSheet'
import { CommandPalette } from '../../palette/CommandPalette/CommandPalette'
import { GlobalShortcuts } from '../GlobalShortcuts'
import { useAppStore } from '../../../stores/appStore'
import './MainLayout.css'

export function MainLayout() {
  const theme = useAppStore((s) => s.theme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  return (
    <div className="main-layout">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Sidebar />
      <div className="main-layout__content">
        <Header />
        <main id="main-content" className="main-layout__main">
          <Outlet />
        </main>
      </div>
      <BottomNav />
      <MoreSheet />
      <QuickAddSheet />
      <CommandPalette />
      <GlobalShortcuts />
    </div>
  )
}

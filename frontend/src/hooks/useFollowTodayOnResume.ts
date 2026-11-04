import { useEffect } from 'react'
import { useAppStore } from '../stores/appStore'

/** Follow the calendar when the app comes back into view: the store decides
 *  whether to move (`followToday`), this only says when to ask. */
export function useFollowTodayOnResume() {
  const followToday = useAppStore((s) => s.followToday)
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') followToday()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', followToday)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', followToday)
    }
  }, [followToday])
}

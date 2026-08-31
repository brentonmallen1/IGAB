import { Component, type ErrorInfo, type ReactNode } from 'react'
import './ErrorBoundary.css'
import { RECOVERABLE_PERSIST_KEYS } from '../../../stores/persistKeys'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Keys whose stored value can make a render crash survive a reload.
 *  Persisted UI selections are replayed on boot, so if one of them is what the
 *  crashing render read, refreshing lands straight back on the same error. */
// From the stores themselves — hardcoding the list here left igab-app out.

/**
 * Catches render errors so a bad component blanks its own region instead of
 * the whole application.
 *
 * This exists because of a real incident: a ReferenceError in the budget
 * filter bar unmounted the entire tree, and because the active view and filter
 * are persisted, reloading reproduced it immediately — leaving no way back in
 * from the UI. Showing the error is the smaller half; the escape hatch is the
 * point.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept for the browser console — there is no error reporting service here,
    // and a self-hosted user debugging their own instance has only this.
    console.error('Unhandled render error:', error, info.componentStack)
  }

  private reload = () => {
    this.setState({ error: null })
    window.location.reload()
  }

  private resetAndReload = () => {
    for (const key of RECOVERABLE_PERSIST_KEYS) {
      try {
        localStorage.removeItem(key)
      } catch {
        // Private browsing, or storage disabled. Reloading is still worth a try.
      }
    }
    this.reload()
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="error-boundary" role="alert">
        <div className="error-boundary__card">
          <h1 className="error-boundary__title">Something went wrong</h1>
          <p className="error-boundary__body">
            A part of the page failed to render. Your data is safe — this is a display problem, and
            nothing was saved or changed.
          </p>
          <pre className="error-boundary__detail">{this.state.error.message}</pre>
          <div className="error-boundary__actions">
            <button type="button" className="error-boundary__btn" onClick={this.reload}>
              Reload
            </button>
            <button
              type="button"
              className="error-boundary__btn error-boundary__btn--primary"
              onClick={this.resetAndReload}
            >
              Reset saved view &amp; reload
            </button>
          </div>
          <p className="error-boundary__hint">
            If reloading lands here again, the second button clears the remembered view, filter and
            report selections — which is usually what a repeating error is stuck on.
          </p>
        </div>
      </div>
    )
  }
}

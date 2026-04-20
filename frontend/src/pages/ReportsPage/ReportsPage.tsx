import { useState } from 'react'
import { useAppStore } from '../../stores/appStore'
import { useSpendingReport, useIncomeExpenseReport, buildExportUrl } from '../../api/reports'
import { SpendingChart } from '../../components/reports/SpendingChart'
import { IncomeExpenseChart } from '../../components/reports/IncomeExpenseChart'
import './ReportsPage.css'

type Tab = 'spending' | 'income-expense'

function defaultDates() {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), 1)
  return {
    start: start.toISOString().slice(0, 10),
    end: today.toISOString().slice(0, 10),
  }
}

export function ReportsPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [tab, setTab] = useState<Tab>('spending')
  const [startDate, setStartDate] = useState(defaultDates().start)
  const [endDate, setEndDate] = useState(defaultDates().end)
  const [months, setMonths] = useState(12)

  const spending = useSpendingReport(budgetId, startDate, endDate)
  const incomeExpense = useIncomeExpenseReport(budgetId, months)

  if (!budgetId) {
    return <div className="reports-page"><div className="reports-empty">Select a budget to view reports.</div></div>
  }

  return (
    <div className="reports-page">
      <div className="reports-header">
        <h1 className="reports-title">Reports</h1>
        <div className="reports-tabs">
          <button
            className={`reports-tab ${tab === 'spending' ? 'active' : ''}`}
            onClick={() => setTab('spending')}
          >
            Spending
          </button>
          <button
            className={`reports-tab ${tab === 'income-expense' ? 'active' : ''}`}
            onClick={() => setTab('income-expense')}
          >
            Income vs Expenses
          </button>
        </div>
      </div>

      {tab === 'spending' && (
        <div className="reports-section">
          <div className="reports-controls">
            <label>
              From
              <input
                type="date"
                className="reports-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </label>
            <label>
              To
              <input
                type="date"
                className="reports-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </label>
            <div className="reports-export">
              <a
                className="reports-btn"
                href={buildExportUrl(budgetId, 'csv', startDate, endDate)}
                download
              >
                Export CSV
              </a>
              <a
                className="reports-btn"
                href={buildExportUrl(budgetId, 'json', startDate, endDate)}
                download
              >
                Export JSON
              </a>
            </div>
          </div>
          {spending.isLoading ? (
            <div className="reports-empty">Loading…</div>
          ) : (
            <SpendingChart
              categories={spending.data?.categories ?? []}
              total={Number(spending.data?.total ?? 0)}
            />
          )}
        </div>
      )}

      {tab === 'income-expense' && (
        <div className="reports-section">
          <div className="reports-controls">
            <label>
              Months
              <select
                className="reports-input"
                value={months}
                onChange={(e) => setMonths(Number(e.target.value))}
              >
                {[3, 6, 12, 24].map((m) => (
                  <option key={m} value={m}>{m} months</option>
                ))}
              </select>
            </label>
          </div>
          {incomeExpense.isLoading ? (
            <div className="reports-empty">Loading…</div>
          ) : (
            <IncomeExpenseChart months={incomeExpense.data?.months ?? []} />
          )}
        </div>
      )}
    </div>
  )
}

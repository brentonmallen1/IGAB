import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, Loader2, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAIStatus, useTestAIConnection, useOllamaModels } from '../../api/ai'
import { useSettings, useUpdateSetting } from '../../api/settings'
import { AIAdvancedSettings } from './AIAdvancedSettings'
import { AIPromptSettings } from './AIPromptSettings'
import './AISettingsPanel.css'

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(0)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export function AISettingsPanel() {
  const { data: appSettings } = useSettings()
  const updateSetting = useUpdateSetting()
  const aiStatus = useAIStatus()
  const testConnection = useTestAIConnection()
  const { data: models, refetch: refetchModels, isFetching: modelsFetching } = useOllamaModels()

  // Settings from DB
  const aiEnabled = appSettings?.find((s) => s.key === 'ai_enabled')?.value === 'true'
  const ollamaHost = appSettings?.find((s) => s.key === 'ollama_host')?.value ?? ''
  const ollamaModel = appSettings?.find((s) => s.key === 'ollama_model')?.value ?? ''

  // Edit state
  const [editHost, setEditHost] = useState('')
  const [editing, setEditing] = useState(false)
  const [editRetention, setEditRetention] = useState('')

  // Sync edit state when settings load
  useEffect(() => {
    if (!editing && ollamaHost) setEditHost(ollamaHost)
  }, [ollamaHost, editing])

  const retentionDays =
    appSettings?.find((s) => s.key === 'ai_activity_retention_days')?.value ?? '30'
  useEffect(() => {
    if (appSettings) setEditRetention(retentionDays)
    // Sync from server once loaded; local edits win afterwards
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appSettings === undefined])

  const retentionValid = /^\d+$/.test(editRetention)

  async function saveRetention() {
    await updateSetting.mutateAsync({
      key: 'ai_activity_retention_days',
      value: String(parseInt(editRetention, 10)),
    })
    toast.success('Saved')
  }

  async function toggleEnabled() {
    const newValue = aiEnabled ? 'false' : 'true'
    await updateSetting.mutateAsync({ key: 'ai_enabled', value: newValue })
    if (newValue === 'true') {
      // Test connection when enabling
      const result = await testConnection.mutateAsync()
      if (result.available) {
        toast.success('AI connected')
        refetchModels()
      } else {
        toast.error('AI enabled but Ollama not reachable — check the host')
      }
    }
  }

  async function saveHost() {
    if (!editHost.trim()) return
    await updateSetting.mutateAsync({ key: 'ollama_host', value: editHost.trim() })
    setEditing(false)
    // Re-test connection
    const result = await testConnection.mutateAsync()
    if (result.available) {
      toast.success('Connected to Ollama')
      refetchModels()
    } else {
      toast.error('Could not connect to Ollama at this host')
    }
  }

  async function handleTestConnection() {
    const result = await testConnection.mutateAsync()
    if (result.available) {
      toast.success('Connected to Ollama')
      refetchModels()
    } else {
      toast.error('Could not connect — is Ollama running?')
    }
  }

  async function selectModel(modelName: string) {
    await updateSetting.mutateAsync({ key: 'ollama_model', value: modelName })
    toast.success(`Model set to ${modelName}`)
  }

  // Status indicator
  const statusIcon = !aiEnabled ? (
    <span className="ai-panel__status ai-panel__status--disabled">Disabled</span>
  ) : aiStatus.isLoading || testConnection.isPending ? (
    <span className="ai-panel__status ai-panel__status--loading">
      <Loader2 size={12} className="spin" /> Checking…
    </span>
  ) : aiStatus.data?.available ? (
    <span className="ai-panel__status ai-panel__status--connected">
      <CheckCircle size={12} /> Connected
    </span>
  ) : (
    <span className="ai-panel__status ai-panel__status--error">
      <XCircle size={12} /> Not connected
    </span>
  )

  return (
    <div className="settings-section" id="ai">
      <div className="settings-section__header">
        <div className="settings-section__title">
          <Zap size={16} />
          AI (Ollama)
        </div>
        {statusIcon}
      </div>
      <div className="settings-section__body">
        {/* Enable toggle */}
        <div className="settings-row">
          <div>
            <div className="settings-row__label">Enable AI features</div>
            <div className="settings-row__desc">
              Receipt scanning, category suggestions, payee normalization
            </div>
          </div>
          <label className="ai-panel__toggle">
            <input
              type="checkbox"
              checked={aiEnabled}
              onChange={toggleEnabled}
              disabled={updateSetting.isPending}
            />
            <span className="ai-panel__toggle-slider" />
          </label>
        </div>

        {aiEnabled && (
          <>
            {/* Host */}
            <div className="settings-row">
              <div>
                <div className="settings-row__label">Ollama Host</div>
                {!editing ? (
                  <div className="settings-row__desc">{ollamaHost || 'http://localhost:11434'}</div>
                ) : (
                  <input
                    type="text"
                    className="settings-input"
                    value={editHost}
                    onChange={(e) => setEditHost(e.target.value)}
                    placeholder="http://localhost:11434"
                    autoFocus
                  />
                )}
              </div>
              {!editing ? (
                <div className="ai-panel__actions">
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => setEditing(true)}
                  >
                    Edit
                  </button>
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={handleTestConnection}
                    disabled={testConnection.isPending}
                  >
                    {testConnection.isPending ? 'Testing…' : 'Test Connection'}
                  </button>
                </div>
              ) : (
                <div className="ai-panel__actions">
                  <button className="settings-btn settings-btn--primary" onClick={saveHost}>
                    Save
                  </button>
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => {
                      setEditing(false)
                      setEditHost(ollamaHost)
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>

            {/* Model picker */}
            <div className="settings-row">
              <div>
                <div className="settings-row__label">Model</div>
                <div className="settings-row__desc">
                  {ollamaModel || 'Select a model'}
                  {models?.find((m) => m.name === ollamaModel)?.capabilities?.length ? (
                    <span className="ai-panel__caps">
                      {models
                        .find((m) => m.name === ollamaModel)
                        ?.capabilities.map((c) => (
                          <span key={c} className="ai-panel__cap">
                            {c}
                          </span>
                        ))}
                    </span>
                  ) : null}
                </div>
              </div>
              <button
                className="settings-btn settings-btn--secondary"
                onClick={() => refetchModels()}
                disabled={modelsFetching}
              >
                {modelsFetching ? 'Loading…' : 'Refresh Models'}
              </button>
            </div>

            {models && models.length > 0 && (
              <div className="ai-panel__models">
                {models.map((m) => (
                  <button
                    key={m.name}
                    className={`ai-panel__model ${m.name === ollamaModel ? 'ai-panel__model--selected' : ''}`}
                    onClick={() => selectModel(m.name)}
                  >
                    <span className="ai-panel__model-name">{m.name}</span>
                    <span className="ai-panel__model-size">{formatBytes(m.size)}</span>
                    {m.capabilities.length > 0 && (
                      <span className="ai-panel__caps">
                        {m.capabilities.map((c) => (
                          <span key={c} className="ai-panel__cap">
                            {c}
                          </span>
                        ))}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {aiStatus.data?.available && !models?.length && !modelsFetching && (
              <div className="ai-panel__empty">
                No models found. Make sure you have pulled at least one model in Ollama.
              </div>
            )}

            <div className="settings-row">
              <div>
                <div className="settings-row__label">Activity log retention</div>
                <div className="settings-row__desc">
                  Finished entries older than this are cleaned up nightly. 0 keeps
                  them forever. Transactions and receipt images are never touched.
                </div>
              </div>
              <div className="ai-panel__actions">
                <input
                  type="number"
                  min={0}
                  className="settings-input ai-panel__retention-input"
                  value={editRetention}
                  onChange={(e) => setEditRetention(e.target.value)}
                  aria-label="Retention in days"
                />
                <span className="ai-panel__retention-unit">days</span>
                <button
                  className="settings-btn settings-btn--secondary"
                  onClick={() => void saveRetention()}
                  disabled={!retentionValid || updateSetting.isPending}
                >
                  Save
                </button>
              </div>
            </div>

            <AIAdvancedSettings />
            <AIPromptSettings />
          </>
        )}
      </div>
    </div>
  )
}

// === STAGE 21.11 BUILD OVERWRITE CONFIRMATION ===
import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import {
  createWebBuildProject,
  desktopJsonToProject,
  downloadJson,
  parseBuildFile,
  projectToDesktopJson,
  safeFilename,
  type WebBuildProject,
  type WebBuildSnapshot,
} from '../buildProject'
import { importRrf } from '../api'
import {
  loadLastBuildName,
  saveLastBuildName,
} from '../browserStorage'
import {
  MAX_BROWSER_BUILDS,
  readBrowserBuilds,
  subscribeBrowserBuilds,
  writeBrowserBuilds,
  type BrowserStoredBuild,
} from '../browserBuildStorage'
import type { JobSummary } from '../types'
import ConfirmDialog from './ConfirmDialog'

function readableError(error: unknown): string {
  return error instanceof Error
    ? error.message
    : String(error)
}

export default function BuildManager({
  snapshot,
  jobs,
  onLoad,
}: {
  snapshot: WebBuildSnapshot
  jobs: JobSummary[]
  onLoad: (snapshot: WebBuildSnapshot) => void
}) {
  const [name, setName] = useState(
    () => loadLastBuildName('我的配裝'),
  )
  const [stored, setStored] = useState<BrowserStoredBuild[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const [rrfImporting, setRrfImporting] = useState(false)
  const [pendingOverwrite, setPendingOverwrite] =
    useState<BrowserStoredBuild | null>(null)

  useEffect(() => {
    const refresh = () => {
      setStored(readBrowserBuilds())
    }

    refresh()
    return subscribeBrowserBuilds(refresh)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(
      () => {
        saveLastBuildName(name)
      },
      120,
    )

    return () =>
      window.clearTimeout(timer)
  }, [name])

  const project = useMemo(
    () => createWebBuildProject(snapshot, name),
    [name, snapshot],
  )

  function commitLocalSave(
    existing: BrowserStoredBuild | null,
  ) {
    const storedBuild: BrowserStoredBuild = {
      id:
        existing?.id ??
        (
          typeof crypto !== 'undefined' &&
          'randomUUID' in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random()}`
        ),
      name: project.name,
      saved_at: project.saved_at,
      project,
    }

    const next = [
      storedBuild,
      ...stored.filter(
        (row) =>
          row.id !== storedBuild.id &&
          row.name !== storedBuild.name,
      ),
    ].slice(0, MAX_BROWSER_BUILDS)

    writeBrowserBuilds(next)
    setStored(next)
    setMessage(
      existing
        ? `已取代同名配裝：${storedBuild.name}`
        : `已存到此瀏覽器：${storedBuild.name}`,
    )
    setError('')
    setPendingOverwrite(null)
  }

  function saveLocal() {
    const existing =
      stored.find(
        (row) => row.name === project.name,
      ) ?? null

    if (existing) {
      setPendingOverwrite(existing)
      setMessage('')
      setError('')
      return
    }

    commitLocalSave(null)
  }

  function loadLocal(row: BrowserStoredBuild) {
    onLoad(row.project.state)
    setName(row.name)
    setMessage(`已載入：${row.name}`)
    setError('')
  }

  function deleteLocal(id: string) {
    const next = stored.filter((row) => row.id !== id)
    writeBrowserBuilds(next)
    setStored(next)
    setMessage('已刪除瀏覽器存檔')
    setError('')
  }

  function exportWeb() {
    const filename = `${safeFilename(project.name)}.robuild.json`
    downloadJson(project, filename)
    setMessage(`已匯出 Web Build：${filename}`)
    setError('')
  }

  async function exportDesktop() {
    try {
      setError('')
      const data = await projectToDesktopJson(project, jobs)
      const filename = `${safeFilename(project.name)}.json`
      downloadJson(data, filename)
      setMessage(`已匯出 Desktop 相容 JSON：${filename}`)
    } catch (exportError) {
      setError(readableError(exportError))
    }
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) {
      return
    }

    setImporting(true)
    setError('')
    setMessage('')

    try {
      const result = await parseBuildFile(await file.text(), jobs)
      onLoad(result.project.state)
      setName(
        result.project.name === 'Desktop 匯入'
          ? file.name.replace(/\.json$/i, '')
          : result.project.name,
      )
      setMessage(
        [
          result.source === 'desktop'
            ? 'Desktop JSON 已載入'
            : 'Web Build 已載入',
          ...result.warnings,
        ].join('；'),
      )
    } catch (importError) {
      setError(`匯入失敗：${readableError(importError)}`)
    } finally {
      setImporting(false)
    }
  }

  function arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer)
    let binary = ''
    const chunkSize = 0x8000
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      binary += String.fromCharCode(
        ...bytes.subarray(offset, offset + chunkSize),
      )
    }
    return btoa(binary)
  }

  async function importRrfFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setRrfImporting(true)
    setError('')
    setMessage('')

    try {
      const response = await importRrf(
        file.name,
        arrayBufferToBase64(await file.arrayBuffer()),
      )
      const result = await desktopJsonToProject(
        response.desktop_json,
        jobs,
      )
      onLoad(result.project.state)

      const buildName = [
        response.meta.character_name,
        response.meta.job_name,
      ]
        .filter(Boolean)
        .join('_')
      if (buildName) setName(buildName)

      setMessage(
        [
          `RRF 已匯入：${response.meta.character_name || file.name}`,
          response.meta.job_name ? `職業 ${response.meta.job_name}` : '',
          `技能 ${response.meta.skill_count}`,
          `Buff ${response.meta.buff_count}`,
          ...response.warnings,
          ...result.warnings,
        ]
          .filter(Boolean)
          .join('；'),
      )
    } catch (importError) {
      setError(`RRF 匯入失敗：${readableError(importError)}`)
    } finally {
      setRrfImporting(false)
    }
  }

  return (
    <details className="build-manager" open>
      <summary>配裝存檔 / Desktop JSON 互通</summary>
      <div className="build-manager-body">
        <div className="build-manager-main">
          <label className="field">
            <span>配裝名稱</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：盧恩龍火 / 法系王卡"
            />
          </label>

          <div className="build-manager-actions">
            <button
              className="button button-primary"
              type="button"
              onClick={saveLocal}
            >
              存到此瀏覽器
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={exportWeb}
            >
              匯出 Web Build
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => void exportDesktop()}
            >
              匯出 Desktop JSON
            </button>
            <label className="button button-secondary file-button">
              {importing ? '匯入中…' : '匯入 JSON'}
              <input
                type="file"
                accept=".json,application/json"
                disabled={importing}
                onChange={(event) => void importFile(event)}
              />
            </label>
            <label className="button button-secondary file-button">
              {rrfImporting ? 'RRF 解析中…' : '匯入 RRF'}
              <input
                type="file"
                accept=".rrf,.txt"
                disabled={rrfImporting}
                onChange={(event) => void importRrfFile(event)}
              />
            </label>
          </div>

          {message && <p className="build-message">{message}</p>}
          {error && <p className="error-text build-message">{error}</p>}

          <p className="build-help">
            Web Build / JSON 都由瀏覽器直接讀寫。RRF 例外：瀏覽器無法直接執行
            RagnarokReplayExample.exe，因此 RRF 會送到目前設定的 FastAPI server
            解析；若 server 是 127.0.0.1 就只在本機，若部署遠端則 Replay
            會傳到該 server。
          </p>
        </div>

        <aside className="local-build-list">
          <div className="local-build-heading">
            <strong>此瀏覽器存檔</strong>
            <span>{stored.length}/{MAX_BROWSER_BUILDS}</span>
          </div>

          {stored.length === 0 ? (
            <p className="muted">還沒有本機快速存檔。</p>
          ) : (
            stored.map((row) => (
              <div className="local-build-row" key={row.id}>
                <button type="button" onClick={() => loadLocal(row)}>
                  <strong>{row.name}</strong>
                  <span>
                    {new Date(row.saved_at).toLocaleString()}
                  </span>
                </button>
                <button
                  className="text-button danger-text"
                  type="button"
                  onClick={() => deleteLocal(row.id)}
                >
                  刪除
                </button>
              </div>
            ))
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={pendingOverwrite !== null}
        title="同名配裝已存在"
        message={
          pendingOverwrite
            ? `此瀏覽器已有配裝「${pendingOverwrite.name}」。取代後舊內容會被目前整套配裝完整覆蓋。是否取代？`
            : ''
        }
        confirmLabel="取代配裝"
        onCancel={() => setPendingOverwrite(null)}
        onConfirm={() => {
          if (pendingOverwrite) {
            commitLocalSave(pendingOverwrite)
          }
        }}
      />
    </details>
  )
}

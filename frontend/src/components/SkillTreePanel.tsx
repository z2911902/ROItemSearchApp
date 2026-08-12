// === STAGE 19 WEB SKILL TREE ===
import { useEffect, useMemo, useState } from 'react'
import { changeSkillTreeLevel, getSkillTree } from '../api'
import type { SkillTreeResponse } from '../types'

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function levelsFromNote(
  note: string,
  tree: SkillTreeResponse | null,
): Record<string, number> {
  if (!tree) return {}
  const codeById = new Map<number, string>()
  tree.nodes.forEach((node) => {
    if (node.skill_id) codeById.set(node.skill_id, node.code)
  })
  const result: Record<string, number> = {}
  const regex = /EnableSkill\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)/g
  for (const match of note.matchAll(regex)) {
    const code = codeById.get(Number(match[1]))
    if (code) result[code] = Number(match[2])
  }
  return result
}

export default function SkillTreePanel({
  apiReady,
  jobId,
  note,
  onNoteChange,
}: {
  apiReady: boolean
  jobId: number | null
  note: string
  onNoteChange: (note: string) => void
}) {
  const [tree, setTree] = useState<SkillTreeResponse | null>(null)
  const [levels, setLevels] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [changing, setChanging] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!apiReady || jobId === null) {
      setTree(null)
      setLevels({})
      return
    }
    const controller = new AbortController()
    void (async () => {
      setLoading(true)
      setError('')
      try {
        const response = await getSkillTree(jobId, controller.signal)
        setTree(response)
        setLevels(levelsFromNote(note, response))
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setTree(null)
          setLevels({})
          setError(readableError(loadError))
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [apiReady, jobId])

  useEffect(() => {
    if (tree) setLevels(levelsFromNote(note, tree))
  }, [note, tree])

  const usedByRegion = useMemo(() => {
    if (!tree) return {} as Record<number, number>
    const nodes = new Map(tree.nodes.map((node) => [node.code, node]))
    const result: Record<number, number> = {}
    Object.entries(levels).forEach(([code, level]) => {
      const node = nodes.get(code)
      if (!node || node.quest_skill) return
      result[node.region] = (result[node.region] ?? 0) + Number(level || 0)
    })
    return result
  }, [levels, tree])

  async function changeLevel(code: string, level: number) {
    if (!tree || jobId === null || changing) return
    setChanging(true)
    setError('')
    setMessage('')
    try {
      const response = await changeSkillTreeLevel(jobId, levels, code, level)
      setLevels(response.levels)
      onNoteChange(response.note)
      setMessage(response.message)
    } catch (changeError) {
      setError(readableError(changeError))
    } finally {
      setChanging(false)
    }
  }

  return (
    <details className="skill-tree-panel">
      <summary>
        技能樹
        {tree && (
          <span>
            {Object.values(levels).reduce(
              (sum, level) => sum + Number(level || 0),
              0,
            )}{' '}
            點
          </span>
        )}
      </summary>

      <div className="skill-tree-body">
        <header className="skill-tree-header">
          <div>
            <div className="eyebrow">DESKTOP SKILL TREE · SHARED CORE</div>
            <h3>{tree?.job_name ?? '技能樹'}</h3>
            <p>
              加減技能會直接改寫 slot 102 的 EnableSkill note，並觸發現有自動計算。
            </p>
          </div>
          <button
            className="button button-secondary"
            type="button"
            disabled={!note.trim()}
            onClick={() => {
              setLevels({})
              onNoteChange('')
              setMessage('技能樹已清空。')
            }}
          >
            清空技能樹
          </button>
        </header>

        {loading && <p className="muted">載入 skill_tree.yml…</p>}
        {error && <p className="error-text">{error}</p>}
        {message && <p className="skill-tree-message">{message}</p>}

        {tree?.groups.map((group) => {
          const nodes = tree.nodes.filter((node) => node.region === group.index)
          const used = usedByRegion[group.index] ?? 0
          return (
            <section className="skill-tree-region" key={group.index}>
              <header>
                <div>
                  <strong>{group.label}</strong>
                  <span>{group.jobs.join(' / ')}</span>
                </div>
                <span
                  className={
                    group.max_points > 0 && used > group.max_points
                      ? 'warning-text'
                      : ''
                  }
                >
                  {used}
                  {group.max_points > 0 ? ` / ${group.max_points}` : ''}
                </span>
              </header>

              <div className="skill-tree-grid">
                {nodes.map((node) => {
                  const level = levels[node.code] ?? 0
                  return (
                    <article
                      className={`skill-tree-node ${
                        level > 0 ? 'skill-tree-node-active' : ''
                      }`}
                      key={node.code}
                    >
                      <div className="skill-tree-node-title">
                        <strong>{node.name}</strong>
                        <small>{node.code}</small>
                      </div>

                      {node.requires.length > 0 && (
                        <div className="skill-tree-requires">
                          前置：
                          {node.requires
                            .map(
                              (requirement) =>
                                `${requirement.name} Lv.${requirement.level}`,
                            )
                            .join('、')}
                        </div>
                      )}

                      <div className="skill-tree-level-row">
                        <button
                          type="button"
                          disabled={changing || node.quest_skill || level <= 0}
                          onClick={() => void changeLevel(node.code, level - 1)}
                        >
                          −
                        </button>
                        <span>
                          {level} / {node.max_level}
                        </span>
                        <button
                          type="button"
                          disabled={
                            changing || node.quest_skill || level >= node.max_level
                          }
                          onClick={() => void changeLevel(node.code, level + 1)}
                        >
                          ＋
                        </button>
                      </div>

                      {node.quest_skill && (
                        <small className="skill-tree-quest">任務 / 靈魂習得</small>
                      )}
                    </article>
                  )
                })}
              </div>
            </section>
          )
        })}

        {!loading && jobId === null && (
          <p className="muted">先選擇職業後即可使用技能樹。</p>
        )}
      </div>
    </details>
  )
}

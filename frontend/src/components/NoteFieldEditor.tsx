// === STAGE 21.10 DESKTOP-LIKE FUNCTION AUTOCOMPLETE ===
import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import type {
  KeyboardEvent,
} from 'react'
import {
  getNoteFunctionMap,
  getNoteFunctions,
  parseNote,
} from '../api'
import type {
  CalculatePayload,
  NoteConditionOperator,
  NoteConditionValue,
  NoteControlFlow,
  NoteFunctionArg,
  NoteFunctionCatalogResponse,
  NoteFunctionDefinition,
  NoteFunctionMapOption,
  NoteParsePayload,
} from '../types'

function readableError(
  error: unknown,
): string {
  return error instanceof Error
    ? error.message
    : String(error)
}

function appendRaw(
  current: string,
  line: string,
): string {
  if (!current) return line

  return current.endsWith('\n')
    ? current + line
    : `${current}\n${line}`
}

function buildParsePayload(
  raw: string,
  slotId: number,
  grade: number,
  refine: number,
  context: CalculatePayload | null,
): NoteParsePayload {
  return {
    note: raw,
    slot_id: slotId,
    grade,
    get_values:
      context?.get_values ?? {},
    refine_inputs: {
      ...(context?.refine_inputs ??
        {}),
      [slotId]: refine,
    },
    context_variables:
      context?.context_variables ??
      {},
    enabled_skill_levels:
      context?.enabled_skill_levels ??
      {},
  }
}

function useParsedNote(
  raw: string,
  enabled: boolean,
  slotId: number,
  grade: number,
  refine: number,
  context: CalculatePayload | null,
) {
  const [lines, setLines] =
    useState<string[]>([])
  const [loading, setLoading] =
    useState(false)
  const [error, setError] =
    useState('')

  useEffect(() => {
    if (!raw.trim()) {
      setLines([])
      setLoading(false)
      setError('')
      return
    }

    if (!enabled) {
      setLoading(false)
      setError(
        'Core API 暫時離線；原始 Lua 已保留。',
      )
      return
    }

    const controller =
      new AbortController()

    setLoading(true)
    setError('')

    const timer = window.setTimeout(
      () => {
        void (async () => {
          try {
            const response =
              await parseNote(
                buildParsePayload(
                  raw,
                  slotId,
                  grade,
                  refine,
                  context,
                ),
                controller.signal,
              )

            if (
              !controller
                .signal.aborted
            ) {
              setLines(
                response.lines,
              )
            }
          } catch (parseError) {
            if (
              !controller
                .signal.aborted
            ) {
              setError(
                readableError(
                  parseError,
                ),
              )
            }
          } finally {
            if (
              !controller
                .signal.aborted
            ) {
              setLoading(false)
            }
          }
        })()
      },
      180,
    )

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [
    context,
    enabled,
    grade,
    raw,
    refine,
    slotId,
  ])

  return {
    lines,
    loading,
    error,
  }
}

function FunctionMapPicker({
  mapName,
  value,
  onChange,
}: {
  mapName: string
  value: string
  onChange: (value: string) => void
}) {
  const [query, setQuery] =
    useState('')
  const [options, setOptions] =
    useState<
      NoteFunctionMapOption[]
    >([])
  const [loading, setLoading] =
    useState(false)

  useEffect(() => {
    if (!mapName) {
      setOptions([])
      return
    }

    const controller =
      new AbortController()

    const timer = window.setTimeout(
      () => {
        void (async () => {
          setLoading(true)

          try {
            const response =
              await getNoteFunctionMap(
                mapName,
                query,
                mapName ===
                    'skill_map' ||
                  mapName ===
                    'skill_map_all'
                  ? 200
                  : 500,
                controller.signal,
              )

            if (
              controller
                .signal.aborted
            ) {
              return
            }

            setOptions(
              response.options,
            )

            if (
              !value &&
              response
                .options
                .length > 0
            ) {
              onChange(
                String(
                  response
                    .options[0]
                    .value,
                ),
              )
            }
          } catch {
            if (
              !controller
                .signal.aborted
            ) {
              setOptions([])
            }
          } finally {
            if (
              !controller
                .signal.aborted
            ) {
              setLoading(false)
            }
          }
        })()
      },
      160,
    )

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [
    mapName,
    query,
    value,
  ])

  const currentExists =
    options.some(
      (option) =>
        String(option.value) ===
        value,
    )

  return (
    <div className="note-map-picker">
      <input
        type="search"
        value={query}
        onChange={(event) =>
          setQuery(
            event.target.value,
          )
        }
        placeholder={
          mapName === 'skill_map' ||
          mapName ===
            'skill_map_all'
            ? '搜尋技能名稱 / ID'
            : '搜尋中文 / 代碼'
        }
      />

      <select
        value={
          currentExists
            ? value
            : ''
        }
        onChange={(event) =>
          onChange(
            event.target.value,
          )
        }
      >
        {!currentExists &&
          value && (
            <option value="">
              目前值 {value}
            </option>
          )}

        {options.map(
          (option) => (
            <option
              key={`${String(
                option.value,
              )}-${option.label}`}
              value={String(
                option.value,
              )}
            >
              {String(
                option.value,
              )}
              {' = '}
              {option.label}
            </option>
          ),
        )}
      </select>

      {loading && (
        <small>
          載入選項…
        </small>
      )}
    </div>
  )
}

function FunctionParam({
  arg,
  value,
  variableName,
  onValueChange,
  onVariableNameChange,
}: {
  arg: NoteFunctionArg
  value: string
  variableName: string
  onValueChange: (
    value: string,
  ) => void
  onVariableNameChange: (
    value: string,
  ) => void
}) {
  if (
    arg.fixed_value !== null
  ) {
    return (
      <label className="note-function-param">
        <span>
          {arg.name ||
            '固定參數'}
        </span>
        <input
          value={
            arg.fixed_value
          }
          readOnly
        />
      </label>
    )
  }

  if (
    arg.type ===
      'var_select'
  ) {
    return (
      <div className="note-function-param note-function-var-param">
        <label>
          <span>
            變數名稱
          </span>
          <input
            value={
              variableName
            }
            onChange={(
              event,
            ) =>
              onVariableNameChange(
                event
                  .target
                  .value,
              )
            }
            placeholder="可留空"
          />
        </label>

        <label>
          <span>
            {arg.name ||
              '來源'}
          </span>
          <FunctionMapPicker
            mapName={arg.map}
            value={value}
            onChange={
              onValueChange
            }
          />
        </label>
      </div>
    )
  }

  if (arg.map) {
    return (
      <label className="note-function-param">
        <span>
          {arg.name ||
            arg.map}
        </span>
        <FunctionMapPicker
          mapName={arg.map}
          value={value}
          onChange={
            onValueChange
          }
        />
      </label>
    )
  }

  return (
    <label className="note-function-param">
      <span>
        {arg.name ||
          '數值'}
      </span>
      <input
        value={value}
        onChange={(event) =>
          onValueChange(
            event.target.value,
          )
        }
        placeholder={
          arg.placeholder ||
          '數字 / 公式'
        }
      />
    </label>
  )
}

function normalizeFunctionSearch(
  text: string,
): string {
  return String(text ?? '')
    .toLocaleLowerCase()
    .replaceAll('％', '%')
    .replaceAll('．', '.')
    .replaceAll('　', ' ')
    .trim()
}

function functionSearchText(
  func: NoteFunctionDefinition,
): string {
  return normalizeFunctionSearch(
    [
      func.name,
      func.syntax,
      func.desc,
      ...func.args.map(
        (arg) => arg.name,
      ),
    ].join(' '),
  )
}

function NoteFunctionBuilder({
  catalog,
  raw,
  onRawChange,
}: {
  catalog:
    NoteFunctionCatalogResponse | null
  raw: string
  onRawChange: (
    raw: string,
  ) => void
}) {
  const [functionInput, setFunctionInput] =
    useState('')
  const [functionPopupOpen, setFunctionPopupOpen] =
    useState(false)
  const [functionSuggestionIndex, setFunctionSuggestionIndex] =
    useState(0)
  const [selectedName, setSelectedName] =
    useState('')
  const [paramValues, setParamValues] =
    useState<Record<number, string>>(
      {},
    )
  const [variableNames, setVariableNames] =
    useState<Record<number, string>>(
      {},
    )

  const [conditionKind, setConditionKind] =
    useState('if')
  const [
    conditionLeft,
    setConditionLeft,
  ] = useState('')
  const [
    conditionOperator,
    setConditionOperator,
  ] = useState('==')
  const [
    conditionRight,
    setConditionRight,
  ] = useState('')

  const selectableFunctions = useMemo(
    () =>
      (catalog?.functions ?? [])
        .filter(
          (func) =>
            !func.separator,
        )
        .slice()
        .sort(
          (left, right) =>
            left.name.localeCompare(
              right.name,
              undefined,
              {
                sensitivity: 'base',
              },
            ),
        ),
    [catalog?.functions],
  )

  const functionSuggestions = useMemo(
    () => {
      const keyword =
        normalizeFunctionSearch(
          functionInput,
        )

      if (!keyword) {
        return []
      }

      return selectableFunctions
        .filter((func) =>
          functionSearchText(
            func,
          ).includes(keyword),
        )
        .slice(0, 12)
    },
    [
      functionInput,
      selectableFunctions,
    ],
  )

  const selected =
    useMemo(
      () =>
        catalog?.functions.find(
          (func) =>
            func.name ===
            selectedName,
        ) ?? null,
      [
        catalog?.functions,
        selectedName,
      ],
    )

  useEffect(() => {
    if (
      selectedName ||
      !catalog
    ) {
      return
    }

    const first =
      selectableFunctions[0]

    if (first) {
      setSelectedName(
        first.name,
      )
    }
  }, [
    catalog,
    selectableFunctions,
    selectedName,
  ])

  useEffect(() => {
    if (!selected) {
      return
    }

    const next:
      Record<number, string> =
        {}

    for (
      const arg
      of selected.args
    ) {
      next[arg.index] =
        arg.fixed_value ??
        (arg.type ===
        'value'
          ? '0'
          : '')
    }

    setParamValues(next)
    setVariableNames({})
  }, [selected])

  useEffect(() => {
    const first =
      catalog
        ?.condition_values?.[0]

    if (
      first &&
      !conditionLeft
    ) {
      setConditionLeft(
        first.syntax,
      )
    }
  }, [
    catalog,
    conditionLeft,
  ])

  function selectFunction(
    func: NoteFunctionDefinition,
  ) {
    setSelectedName(func.name)
    setFunctionInput(func.name)
    setFunctionPopupOpen(false)
    setFunctionSuggestionIndex(0)
  }

  function handleFunctionInput(
    value: string,
  ) {
    setFunctionInput(value)
    setFunctionSuggestionIndex(0)
    setFunctionPopupOpen(
      Boolean(value.trim()),
    )
  }

  function handleFunctionKeyDown(
    event:
      KeyboardEvent<HTMLInputElement>,
  ) {
    if (
      !functionPopupOpen ||
      functionSuggestions.length === 0
    ) {
      if (
        event.key === 'ArrowDown' &&
        functionSuggestions.length > 0
      ) {
        event.preventDefault()
        setFunctionPopupOpen(true)
      }
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setFunctionSuggestionIndex(
        (current) =>
          Math.min(
            current + 1,
            functionSuggestions.length - 1,
          ),
      )
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setFunctionSuggestionIndex(
        (current) =>
          Math.max(
            current - 1,
            0,
          ),
      )
      return
    }

    if (
      event.key === 'Enter' ||
      event.key === 'Tab'
    ) {
      const candidate =
        functionSuggestions[
          functionSuggestionIndex
        ] ??
        functionSuggestions[0]

      if (candidate) {
        event.preventDefault()
        selectFunction(candidate)
      }
      return
    }

    if (event.key === 'Escape') {
      event.preventDefault()
      setFunctionPopupOpen(false)
    }
  }

  function addFunction() {
    if (
      !selected ||
      selected.separator
    ) {
      return
    }

    const values =
      selected.args.map(
        (arg) =>
          arg.fixed_value ??
          paramValues[
            arg.index
          ] ??
          '',
      )

    const base =
      `${selected.name}(` +
      `${values.join(', ')})`

    const varArg =
      selected.args.find(
        (arg) =>
          arg.type ===
          'var_select',
      )

    const variable =
      varArg
        ? (
            variableNames[
              varArg.index
            ] ?? ''
          ).trim()
        : ''

    const result =
      variable
        ? `${variable} = ${base}`
        : base

    onRawChange(
      appendRaw(
        raw,
        result,
      ),
    )
  }

  function addCondition() {
    const kind =
      conditionKind

    if (
      kind === 'else' ||
      kind === 'end'
    ) {
      onRawChange(
        appendRaw(
          raw,
          kind,
        ),
      )
      return
    }

    const left =
      conditionLeft.trim() ||
      '條件'
    const right =
      conditionRight.trim()
    const condition =
      right
        ? `${left} ${conditionOperator} ${right}`
        : left

    if (kind === 'if') {
      onRawChange(
        appendRaw(
          raw,
          `if ${condition} then\n    \nend`,
        ),
      )
    } else {
      onRawChange(
        appendRaw(
          raw,
          `elseif ${condition} then`,
        ),
      )
    }
  }

  return (
    <section className="note-function-builder">
      <header>
        <div>
          <strong>
            函數輸入
          </strong>
          <small>
            與 Desktop
            function_defs
            使用相同函數與中文參數
          </small>
        </div>
      </header>

      <div className="note-function-choice-grid">
        <div className="note-function-autocomplete">
          <label>
            <span>
              直接輸入 / 補完
            </span>

            <input
              type="text"
              value={functionInput}
              autoComplete="off"
              spellCheck={false}
              onFocus={() =>
                setFunctionPopupOpen(
                  Boolean(
                    functionInput.trim(),
                  ),
                )
              }
              onBlur={() => {
                window.setTimeout(
                  () =>
                    setFunctionPopupOpen(
                      false,
                    ),
                  120,
                )
              }}
              onChange={(event) =>
                handleFunctionInput(
                  event.target.value,
                )
              }
              onKeyDown={
                handleFunctionKeyDown
              }
              placeholder="例如 adde → AddExtParam"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={
                functionPopupOpen &&
                functionSuggestions.length > 0
              }
              aria-controls="note-function-suggestions"
            />
          </label>

          {functionPopupOpen &&
            functionInput.trim() &&
            (
              <div
                id="note-function-suggestions"
                className="note-function-suggestions"
                role="listbox"
              >
                {functionSuggestions.length > 0 ? (
                  functionSuggestions.map(
                    (func, index) => (
                      <button
                        key={func.name}
                        type="button"
                        role="option"
                        aria-selected={
                          index ===
                          functionSuggestionIndex
                        }
                        className={`note-function-suggestion ${
                          index ===
                          functionSuggestionIndex
                            ? 'note-function-suggestion-active'
                            : ''
                        }`}
                        onMouseDown={(event) =>
                          event.preventDefault()
                        }
                        onMouseEnter={() =>
                          setFunctionSuggestionIndex(
                            index,
                          )
                        }
                        onClick={() =>
                          selectFunction(
                            func,
                          )
                        }
                      >
                        <strong>
                          {func.name}
                        </strong>
                        <code>
                          {func.syntax}
                        </code>
                        <small>
                          {func.desc ||
                            '無中文說明'}
                        </small>
                      </button>
                    ),
                  )
                ) : (
                  <div className="note-function-suggestion-empty">
                    沒有符合「
                    {functionInput.trim()}
                    」的函數
                  </div>
                )}
              </div>
            )}
        </div>

        <label className="note-function-select-field">
          <span>
            完整函數選單
          </span>
          <select
            value={selectedName}
            onChange={(event) => {
              const func =
                selectableFunctions.find(
                  (item) =>
                    item.name ===
                    event.target.value,
                )

              if (func) {
                selectFunction(func)
              }
            }}
          >
            {selectableFunctions.map(
              (func) => (
                <option
                  key={`${func.name}-${func.desc}`}
                  value={func.name}
                >
                  {func.name}
                  {'｜'}
                  {func.desc ||
                    func.syntax}
                </option>
              ),
            )}
          </select>
        </label>
      </div>

      {selected &&
        !selected.separator && (
          <>
            <div className="note-function-description">
              <strong>
                {selected.desc ||
                  selected.name}
              </strong>
              <code>
                {selected.syntax}
              </code>
            </div>

            <div className="note-function-params">
              {selected.args.map(
                (arg) => (
                  <FunctionParam
                    key={
                      arg.index
                    }
                    arg={arg}
                    value={
                      paramValues[
                        arg.index
                      ] ?? ''
                    }
                    variableName={
                      variableNames[
                        arg.index
                      ] ?? ''
                    }
                    onValueChange={(
                      value,
                    ) =>
                      setParamValues(
                        (
                          current,
                        ) => ({
                          ...current,
                          [arg.index]:
                            value,
                        }),
                      )
                    }
                    onVariableNameChange={(
                      value,
                    ) =>
                      setVariableNames(
                        (
                          current,
                        ) => ({
                          ...current,
                          [arg.index]:
                            value,
                        }),
                      )
                    }
                  />
                ),
              )}
            </div>

            <button
              className="button button-secondary"
              type="button"
              onClick={
                addFunction
              }
            >
              加入原始 Lua
            </button>
          </>
        )}

      <div className="note-condition-builder">
        <strong>
          條件輸入
        </strong>

        <div className="note-condition-grid">
          <select
            value={
              conditionKind
            }
            onChange={(event) =>
              setConditionKind(
                event
                  .target
                  .value,
              )
            }
          >
            {(catalog?.control_flow ??
              []).map(
              (
                flow:
                  NoteControlFlow,
              ) => (
                <option
                  key={
                    flow.key
                  }
                  value={
                    flow.key
                  }
                >
                  {flow.display}
                </option>
              ),
            )}
          </select>

          {conditionKind !==
            'else' &&
            conditionKind !==
              'end' && (
              <>
                <select
                  value={
                    conditionLeft
                  }
                  onChange={(
                    event,
                  ) =>
                    setConditionLeft(
                      event
                        .target
                        .value,
                    )
                  }
                >
                  {(catalog
                    ?.condition_values ??
                    []).map(
                    (
                      row:
                        NoteConditionValue,
                    ) => (
                      <option
                        key={
                          row.key
                        }
                        value={
                          row.syntax
                        }
                      >
                        {row.label}
                        {'｜'}
                        {row.syntax}
                      </option>
                    ),
                  )}
                </select>

                <select
                  value={
                    conditionOperator
                  }
                  onChange={(
                    event,
                  ) =>
                    setConditionOperator(
                      event
                        .target
                        .value,
                    )
                  }
                >
                  {(catalog
                    ?.condition_operators ??
                    []).map(
                    (
                      row:
                        NoteConditionOperator,
                    ) => (
                      <option
                        key={
                          row.value
                        }
                        value={
                          row.value
                        }
                      >
                        {row.value}
                        {' '}
                        {row.label}
                      </option>
                    ),
                  )}
                </select>

                <input
                  value={
                    conditionRight
                  }
                  onChange={(
                    event,
                  ) =>
                    setConditionRight(
                      event
                        .target
                        .value,
                    )
                  }
                  placeholder="數值 / 變數 / 公式"
                />
              </>
            )}

          <button
            className="button button-secondary"
            type="button"
            onClick={
              addCondition
            }
          >
            插入條件
          </button>
        </div>
      </div>
    </section>
  )
}

function NoteEditorModal({
  open,
  raw,
  apiReady,
  slotId,
  grade,
  refine,
  context,
  title,
  onCancel,
  onApply,
}: {
  open: boolean
  raw: string
  apiReady: boolean
  slotId: number
  grade: number
  refine: number
  context: CalculatePayload | null
  title: string
  onCancel: () => void
  onApply: (
    raw: string,
  ) => void
}) {
  const [draft, setDraft] =
    useState(raw)
  const [catalog, setCatalog] =
    useState<
      NoteFunctionCatalogResponse | null
    >(null)
  const [catalogError, setCatalogError] =
    useState('')

  useEffect(() => {
    if (open) {
      setDraft(raw)
    }
  }, [
    open,
    raw,
  ])

  useEffect(() => {
    if (
      !open ||
      !apiReady
    ) {
      return
    }

    const controller =
      new AbortController()

    void (async () => {
      try {
        const response =
          await getNoteFunctions(
            '',
            controller.signal,
          )

        if (
          !controller
            .signal.aborted
        ) {
          setCatalog(
            response,
          )
          setCatalogError('')
        }
      } catch (error) {
        if (
          !controller
            .signal.aborted
        ) {
          setCatalogError(
            readableError(error),
          )
        }
      }
    })()

    return () =>
      controller.abort()
  }, [
    apiReady,
    open,
  ])

  const preview = useParsedNote(
    draft,
    open && apiReady,
    slotId,
    grade,
    refine,
    context,
  )

  if (!open) {
    return null
  }

  return (
    <div
      className="note-editor-backdrop"
      role="presentation"
    >
      <section
        className="note-editor-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${title} 詞條編輯`}
      >
        <header className="note-editor-header">
          <div>
            <strong>
              {title}
              {' · '}
              詞條編輯
            </strong>
            <small>
              顯示時解析中文；編輯時保留原始 Lua
            </small>
          </div>

          <button
            className="button button-secondary"
            type="button"
            onClick={onCancel}
          >
            關閉
          </button>
        </header>

        <div className="note-editor-layout">
          <div className="note-editor-input-column">
            {catalogError && (
              <p className="error-text compact-message">
                函數清單：
                {catalogError}
              </p>
            )}

            <NoteFunctionBuilder
              catalog={catalog}
              raw={draft}
              onRawChange={
                setDraft
              }
            />

            <label className="field note-raw-editor">
              <span>
                原始 Lua
              </span>
              <textarea
                value={draft}
                onChange={(
                  event,
                ) =>
                  setDraft(
                    event
                      .target
                      .value,
                  )
                }
                spellCheck={
                  false
                }
                rows={14}
                placeholder={
                  '例如：\nAddExtParam(0, 103, 10)'
                }
              />
              <small>
                儲存到 slot.note 的永遠是這份原始文字。
              </small>
            </label>
          </div>

          <aside className="note-editor-preview-column">
            <header>
              <strong>
                中文解析預覽
              </strong>
              <small>
                使用同一個 Python Core parser
              </small>
            </header>

            {preview.loading && (
              <p className="muted compact-message">
                解析中…
              </p>
            )}

            {preview.error && (
              <p className="error-text compact-message">
                {preview.error}
              </p>
            )}

            {draft.trim() ? (
              <pre className="note-parsed-output note-parsed-output-modal">
                {preview.lines
                  .length > 0
                  ? preview.lines.join(
                      '\n',
                    )
                  : preview.loading
                    ? ''
                    : '目前沒有可解析的中文效果。'}
              </pre>
            ) : (
              <p className="muted">
                尚未輸入詞條。
              </p>
            )}
          </aside>
        </div>

        <footer className="note-editor-footer">
          <button
            className="button button-secondary"
            type="button"
            onClick={() =>
              setDraft('')
            }
          >
            清空原始 Lua
          </button>

          <div>
            <button
              className="button button-secondary"
              type="button"
              onClick={onCancel}
            >
              取消
            </button>

            <button
              className="button"
              type="button"
              onClick={() =>
                onApply(draft)
              }
            >
              套用到詞條
            </button>
          </div>
        </footer>
      </section>
    </div>
  )
}

export default function NoteFieldEditor({
  raw,
  apiReady,
  slotId,
  grade,
  refine,
  context,
  title,
  onChange,
}: {
  raw: string
  apiReady: boolean
  slotId: number
  grade: number
  refine: number
  context: CalculatePayload | null
  title: string
  onChange: (
    raw: string,
  ) => void
}) {
  const [open, setOpen] =
    useState(false)

  const preview = useParsedNote(
    raw,
    apiReady,
    slotId,
    grade,
    refine,
    context,
  )

  return (
    <>
      <section className="note-display-card">
        <header>
          <div>
            <strong>
              詞條
            </strong>
            <small>
              畫面顯示中文解析結果
            </small>
          </div>

          <button
            className="button button-secondary"
            type="button"
            onClick={() =>
              setOpen(true)
            }
          >
            {raw.trim()
              ? '編輯詞條 / 函數輸入'
              : '新增詞條 / 函數輸入'}
          </button>
        </header>

        {raw.trim() ? (
          <>
            {preview.loading &&
              preview.lines
                .length === 0 && (
                <p className="muted compact-message">
                  解析詞條中…
                </p>
              )}

            {preview.error && (
              <p className="error-text compact-message">
                {preview.error}
              </p>
            )}

            <pre className="note-parsed-output">
              {preview.lines
                .length > 0
                ? preview.lines.join(
                    '\n',
                  )
                : preview.loading
                  ? ''
                  : '目前沒有可解析的中文效果。'}
            </pre>
          </>
        ) : (
          <p className="muted compact-message">
            尚未設定詞條。
          </p>
        )}
      </section>

      <NoteEditorModal
        open={open}
        raw={raw}
        apiReady={apiReady}
        slotId={slotId}
        grade={grade}
        refine={refine}
        context={context}
        title={title}
        onCancel={() =>
          setOpen(false)
        }
        onApply={(nextRaw) => {
          onChange(nextRaw)
          setOpen(false)
        }}
      />
    </>
  )
}

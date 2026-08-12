// === STAGE 21.11 CONFIRM DIALOG ===
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '取代',
  cancelLabel = '取消',
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null

  return (
    <div
      className="confirm-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onCancel()
        }
      }}
    >
      <section
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
      >
        <header>
          <strong id="confirm-dialog-title">{title}</strong>
        </header>

        <p id="confirm-dialog-message">{message}</p>

        <footer>
          <button
            className="button button-secondary"
            type="button"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>

          <button
            className="button button-primary confirm-dialog-primary"
            type="button"
            onClick={onConfirm}
            autoFocus
          >
            {confirmLabel}
          </button>
        </footer>
      </section>
    </div>
  )
}

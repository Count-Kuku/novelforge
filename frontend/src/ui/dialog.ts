import { shallowRef } from 'vue'

export type DialogTone = 'default' | 'danger'

export interface DialogRequest {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: DialogTone
  input?: {
    label: string
    initialValue?: string
    placeholder?: string
    match?: string
  }
}

export const dialogState = shallowRef<DialogRequest | null>(null)

let resolveDialog: ((value: boolean | string | null) => void) | null = null

function openDialog(request: DialogRequest): Promise<boolean | string | null> {
  if (resolveDialog) resolveDialog(null)
  dialogState.value = request
  return new Promise((resolve) => {
    resolveDialog = resolve
  })
}

export function closeDialog(value: boolean | string | null) {
  const resolve = resolveDialog
  resolveDialog = null
  dialogState.value = null
  resolve?.(value)
}

export const dialog = {
  async confirm(request: DialogRequest): Promise<boolean> {
    return (await openDialog(request)) === true
  },

  async prompt(request: DialogRequest & { input: NonNullable<DialogRequest['input']> }): Promise<string | null> {
    const result = await openDialog(request)
    return typeof result === 'string' ? result : null
  },
}

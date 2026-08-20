import { ref } from 'vue'

export type NotificationTone = 'success' | 'error' | 'info'

export interface AppNotification {
  id: number
  message: string
  tone: NotificationTone
}

export const notifications = ref<AppNotification[]>([])

let nextNotificationId = 1

export function dismissNotification(id: number) {
  notifications.value = notifications.value.filter((item) => item.id !== id)
}

export function notify(message: string, tone: NotificationTone = 'info') {
  const item = { id: nextNotificationId++, message, tone }
  notifications.value = [...notifications.value, item]
  globalThis.setTimeout(() => dismissNotification(item.id), 4200)
}

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { backendApi } from '@/lib/http'

type EventItem = {
  event_id: string
  title: string
  status: string
  platform: string
  scope: string | null
  group_count: number
  source_count: number
  stance_type: string
  stance_summary: string
  last_activity_at: string
  updated_at: string
}

type EventDetail = EventItem & {
  root_cause: string
  analysis: {
    timeline?: Array<Record<string, unknown>>
    viewpoints?: Array<Record<string, unknown>>
    key_facts?: string[]
    uncertainties?: string[]
  }
  groups: Array<Record<string, unknown>>
  sources: Array<Record<string, unknown>>
}

export function GroupEventsPage() {
  const { t } = useTranslation()
  const [events, setEvents] = useState<EventItem[]>([])
  const [selected, setSelected] = useState<EventDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadEvents = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setEvents(await backendApi.get<EventItem[]>('/api/webui/events'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('groupEvents.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void loadEvents()
  }, [loadEvents])

  const openDetail = async (eventId: string) => {
    try {
      setSelected(await backendApi.get<EventDetail>(`/api/webui/events/${encodeURIComponent(eventId)}`))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('groupEvents.loadFailed'))
    }
  }

  return (
    <main className="container mx-auto space-y-6 p-4 md:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t('groupEvents.title')}</h1>
          <p className="text-muted-foreground mt-1 text-sm">{t('groupEvents.description')}</p>
        </div>
        <button className="border-input rounded-md border px-3 py-2 text-sm" onClick={() => void loadEvents()}>
          {t('groupEvents.refresh')}
        </button>
      </div>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      {loading ? <p className="text-muted-foreground text-sm">{t('groupEvents.loading')}</p> : null}
      {!loading && events.length === 0 ? <p className="text-muted-foreground text-sm">{t('groupEvents.empty')}</p> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {events.map((event) => (
          <Card key={event.event_id} className="cursor-pointer transition hover:shadow-md" onClick={() => void openDetail(event.event_id)}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <CardTitle className="text-base">{event.title || event.event_id}</CardTitle>
                <Badge variant="secondary">{event.status}</Badge>
              </div>
            </CardHeader>
            <CardContent className="text-muted-foreground space-y-2 text-sm">
              <p>{event.stance_summary || t('groupEvents.noStance')}</p>
              <p>{t('groupEvents.sourceCount', { count: event.source_count })} · {t('groupEvents.groups', { count: event.group_count })}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      {selected ? (
        <Card>
          <CardHeader><CardTitle>{selected.title || selected.event_id}</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm">
            <section><h2 className="font-medium">{t('groupEvents.rootCause')}</h2><p className="text-muted-foreground mt-1">{selected.root_cause || t('groupEvents.pending')}</p></section>
            <section><h2 className="font-medium">{t('groupEvents.stance')}</h2><p className="text-muted-foreground mt-1">{selected.stance_summary || t('groupEvents.noStance')}</p></section>
            <section><h2 className="font-medium">{t('groupEvents.viewpoints')}</h2><pre className="bg-muted mt-1 max-h-72 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap">{JSON.stringify(selected.analysis.viewpoints ?? [], null, 2)}</pre></section>
            <section><h2 className="font-medium">{t('groupEvents.timeline')}</h2><pre className="bg-muted mt-1 max-h-72 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap">{JSON.stringify(selected.analysis.timeline ?? [], null, 2)}</pre></section>
            <section>
              <h2 className="font-medium">{t('groupEvents.sources')}</h2>
              <div className="mt-2 space-y-2">
                {selected.sources.map((source, index) => (
                  <article key={`${String(source.session_id)}:${String(source.message_id)}:${index}`} className="border-border rounded-md border p-3">
                    <p className="text-muted-foreground text-xs">{String(source.timestamp)} · {t('groupEvents.groupId')}: {String(source.group_id)} · {t('groupEvents.sourceId')}: {String(source.message_id)}</p>
                    <p className="mt-1 whitespace-pre-wrap">{String(source.text_snapshot)}</p>
                  </article>
                ))}
              </div>
            </section>
          </CardContent>
        </Card>
      ) : null}
    </main>
  )
}

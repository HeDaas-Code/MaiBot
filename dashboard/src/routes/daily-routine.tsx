import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { backendApi } from '@/lib/http'

type Activity = {
  activity_id: string
  name: string
  activity_type: string
  scheduled_start: string
  scheduled_end: string
  status: string
}

type Snapshot = {
  account_key: string
  platform: string
  account_id: string
  timezone: string
  day_key: string
  current_activity: Activity | null
  activities: Activity[]
  status_label: string
  interaction_count: number
  last_sleep_quality: number
  updated_at: string
}

type Draft = {
  draft_id: string
  activity_id: string | null
  draft_type: string
  title: string
  body: string
  source_refs: unknown[]
  status: string
  created_at: string
  expires_at: string | null
}

type Overview = {
  enabled: boolean
  snapshots: Snapshot[]
  drafts: Draft[]
}

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

export function DailyRoutinePage() {
  const { t } = useTranslation()
  const [overview, setOverview] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setOverview(await backendApi.get<Overview>('/api/webui/daily-routine/overview'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('dailyRoutine.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  return (
    <main className="container mx-auto space-y-6 p-4 md:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t('dailyRoutine.title')}</h1>
          <p className="text-muted-foreground mt-1 text-sm">{t('dailyRoutine.description')}</p>
        </div>
        <button
          className="border-input rounded-md border px-3 py-2 text-sm"
          onClick={() => void loadOverview()}
        >
          {t('dailyRoutine.refresh')}
        </button>
      </div>
      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      {loading ? (
        <p className="text-muted-foreground text-sm">{t('dailyRoutine.loading')}</p>
      ) : null}
      {!loading && overview && !overview.enabled ? (
        <p className="text-muted-foreground text-sm">{t('dailyRoutine.disabled')}</p>
      ) : null}
      {!loading && overview && overview.snapshots.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t('dailyRoutine.noAccounts')}</p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {overview?.snapshots.map((snapshot) => (
          <Card key={snapshot.account_key}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <CardTitle className="text-base">
                  {snapshot.platform}:{snapshot.account_id || t('dailyRoutine.defaultAccount')}
                </CardTitle>
                <Badge variant="secondary">{snapshot.status_label}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <p className="text-muted-foreground">
                {snapshot.day_key} · {snapshot.timezone} ·{' '}
                {t('dailyRoutine.interactions', { count: snapshot.interaction_count })}
              </p>
              <section>
                <h2 className="font-medium">{t('dailyRoutine.timeline')}</h2>
                <div className="mt-2 space-y-2">
                  {snapshot.activities.map((activity) => (
                    <div key={activity.activity_id} className="border-border rounded-md border p-2">
                      <div className="flex items-center justify-between gap-2">
                        <span>{activity.name}</span>
                        <Badge variant={activity.status === 'active' ? 'default' : 'outline'}>
                          {activity.status}
                        </Badge>
                      </div>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {formatTime(activity.scheduled_start)} –{' '}
                        {formatTime(activity.scheduled_end)}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t('dailyRoutine.drafts')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {overview?.drafts.length ? (
            overview.drafts.map((draft) => (
              <article key={draft.draft_id} className="border-border rounded-md border p-3">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-medium">{draft.title || t('dailyRoutine.untitled')}</h2>
                  <Badge variant="outline">{draft.draft_type}</Badge>
                </div>
                <p className="mt-2 text-sm whitespace-pre-wrap">{draft.body}</p>
                <p className="text-muted-foreground mt-2 text-xs">{formatTime(draft.created_at)}</p>
              </article>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">{t('dailyRoutine.noDrafts')}</p>
          )}
        </CardContent>
      </Card>
    </main>
  )
}

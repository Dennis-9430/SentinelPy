import { useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Loader2 } from "lucide-react"

// ── Types ────────────────────────────────────────────────────────────────

interface FeedResponse {
  name: string
  status: string
  supported_types: string[]
}

interface FeedsResponse {
  feeds: FeedResponse[]
}

interface IOCResultData {
  indicator: string
  ioc_type: string
  confidence: number
  provider: string
}

interface IOCEntry {
  id: string
  indicator: string
  ioc_type: string
  provider: string
  confidence: number
  first_seen: string | null
  last_seen: string | null
  expires_at: string | null
}

interface IOCsResponse {
  iocs: IOCEntry[]
  total: number
}

// ── Helpers ──────────────────────────────────────────────────────────────

function confidenceColor(confidence: number): string {
  if (confidence >= 80) return "bg-red-600/15 text-red-700 dark:text-red-400"
  if (confidence >= 50) return "bg-yellow-600/15 text-yellow-700 dark:text-yellow-400"
  return "bg-green-600/15 text-green-700 dark:text-green-400"
}

function statusColor(status: string): string {
  if (status === "active") return "bg-green-600/15 text-green-700 dark:text-green-400"
  if (status === "error") return "bg-red-600/15 text-red-700 dark:text-red-400"
  return "text-muted-foreground"
}

// ── Component ────────────────────────────────────────────────────────────

export default function ThreatIntelPage() {
  // ── Lookup state ─────────────────────────────────────────────────────
  const [lookupIndicator, setLookupIndicator] = useState("")
  const [lookupType, setLookupType] = useState("ip")
  const [lookupResult, setLookupResult] = useState<IOCResultData | null>(null)
  const [lookupError, setLookupError] = useState<string | null>(null)

  // ── IOC pagination ───────────────────────────────────────────────────
  const [iocPage, setIocPage] = useState(0)
  const iocLimit = 20

  // ── Fetch feeds ──────────────────────────────────────────────────────
  const { data: feedsData, isLoading: feedsLoading } = useQuery({
    queryKey: ["ti-feeds"],
    queryFn: () => apiFetch<FeedsResponse>("/threat-intel/feeds"),
  })

  // ── Fetch IOCs ───────────────────────────────────────────────────────
  const { data: iocsData, isLoading: iocsLoading } = useQuery({
    queryKey: ["ti-iocs", iocPage],
    queryFn: () =>
      apiFetch<IOCsResponse>(
        `/threat-intel/iocs?limit=${iocLimit}&offset=${iocPage * iocLimit}`,
      ),
  })

  // ── Lookup mutation ──────────────────────────────────────────────────
  const lookupMutation = useMutation({
    mutationFn: (vars: { indicator: string; ioc_type: string }) =>
      apiFetch<IOCResultData>("/threat-intel/lookup", {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: (data) => {
      setLookupResult(data)
      setLookupError(null)
    },
    onError: (err: Error & { status?: number }) => {
      setLookupResult(null)
      setLookupError(err.message || "Lookup failed")
    },
  })

  function handleLookup() {
    if (!lookupIndicator.trim()) return
    lookupMutation.mutate({
      indicator: lookupIndicator.trim(),
      ioc_type: lookupType,
    })
  }

  // ── Render ───────────────────────────────────────────────────────────

  const feeds = feedsData?.feeds ?? []
  const iocs = iocsData?.iocs ?? []
  const iocTotal = iocsData?.total ?? 0
  const iocTotalPages = Math.max(1, Math.ceil(iocTotal / iocLimit))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Threat Intelligence</h1>

      {/* ── Provider Status Cards ─────────────────────────────────────── */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Providers</h2>
        {feedsLoading ? (
          <div className="flex h-24 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : feeds.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No TI providers registered. Configure API keys in the server
              environment.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {feeds.map((feed) => (
              <Card key={feed.name}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-base">
                    <span className="capitalize">{feed.name}</span>
                    <Badge className={statusColor(feed.status)}>
                      {feed.status}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground">
                    Supported types:
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {feed.supported_types.map((t) => (
                      <Badge key={t} variant="outline" className="text-xs">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* ── Manual Lookup Form ────────────────────────────────────────── */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Manual Lookup</h2>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[200px]">
                <label
                  htmlFor="ti-indicator"
                  className="mb-1 block text-sm font-medium"
                >
                  Indicator
                </label>
                <Input
                  id="ti-indicator"
                  placeholder="e.g. 8.8.8.8, evil.com, d41d8cd98f..."
                  value={lookupIndicator}
                  onChange={(e) => setLookupIndicator(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleLookup()
                  }}
                />
              </div>
              <div className="w-36">
                <label className="mb-1 block text-sm font-medium">Type</label>
                <Select value={lookupType} onValueChange={setLookupType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ip">IP</SelectItem>
                    <SelectItem value="domain">Domain</SelectItem>
                    <SelectItem value="hash">Hash</SelectItem>
                    <SelectItem value="url">URL</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                onClick={handleLookup}
                disabled={lookupMutation.isPending || !lookupIndicator.trim()}
              >
                {lookupMutation.isPending ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : null}
                Lookup
              </Button>
            </div>

            {/* Lookup result */}
            {lookupError && (
              <div className="mt-4 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {lookupError}
              </div>
            )}
            {lookupResult && (
              <div className="mt-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Indicator</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Provider</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="font-mono">
                        {lookupResult.indicator}
                      </TableCell>
                      <TableCell>{lookupResult.ioc_type}</TableCell>
                      <TableCell>
                        <Badge className={confidenceColor(lookupResult.confidence)}>
                          {lookupResult.confidence}
                        </Badge>
                      </TableCell>
                      <TableCell>{lookupResult.provider}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* ── Cached IOCs Table ─────────────────────────────────────────── */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Cached IOCs</h2>
        <Card>
          <CardContent className="p-0">
            {iocsLoading ? (
              <div className="flex h-48 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : iocs.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                No cached IOCs yet. Run a lookup or wait for pipeline
                enrichment.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Indicator</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Confidence</TableHead>
                    <TableHead>First Seen</TableHead>
                    <TableHead>Last Seen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {iocs.map((ioc) => (
                    <TableRow key={ioc.id}>
                      <TableCell className="font-mono text-xs">
                        {ioc.indicator}
                      </TableCell>
                      <TableCell>{ioc.ioc_type}</TableCell>
                      <TableCell>{ioc.provider}</TableCell>
                      <TableCell>
                        <Badge className={confidenceColor(ioc.confidence)}>
                          {ioc.confidence}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {ioc.first_seen
                          ? new Date(ioc.first_seen).toLocaleDateString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {ioc.last_seen
                          ? new Date(ioc.last_seen).toLocaleDateString()
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Pagination */}
        {iocTotal > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Total: <span className="font-medium">{iocTotal}</span> IOC
              {iocTotal !== 1 ? "s" : ""}
            </p>
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="text-xs font-normal">
                Page {iocPage + 1} of {iocTotalPages}
              </Badge>
              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={iocPage <= 0}
                  onClick={() => setIocPage((p) => Math.max(0, p - 1))}
                >
                  Prev
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={iocPage + 1 >= iocTotalPages}
                  onClick={() => setIocPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

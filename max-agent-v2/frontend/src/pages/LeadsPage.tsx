import { useState, useEffect } from 'react'
import axios from 'axios'
import { Card, CardContent } from "@/components/ui/card"
import { Search, Filter, Phone, Mail, MessageCircle, TrendingUp } from "lucide-react"

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
    active:      { label: 'Ativo',           color: 'bg-green-100 text-green-700 border-green-200' },
    negotiating: { label: 'Em negociação',   color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
    lost:        { label: 'Perdido',         color: 'bg-red-100 text-red-700 border-red-200' },
    converted:   { label: 'Convertido',      color: 'bg-blue-100 text-blue-700 border-blue-200' },
}

function ScoreBar({ score }: { score: number }) {
    const color =
        score >= 75 ? 'bg-red-500' :
        score >= 50 ? 'bg-yellow-500' : 'bg-blue-500'
    return (
        <div className="flex items-center gap-2">
            <div className="w-20 h-2 rounded-full bg-muted overflow-hidden">
                <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
            </div>
            <span className={`text-xs font-bold ${
                score >= 75 ? 'text-red-500' : score >= 50 ? 'text-yellow-500' : 'text-blue-500'
            }`}>{score}</span>
        </div>
    )
}

export default function ClientesPage() {
    const [leads, setLeads] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState('')

    useEffect(() => {
        axios.get('/api/dashboard/leads')
            .then(res => {
                setLeads(res.data)
                setLoading(false)
            })
            .catch(() => setLoading(false))
    }, [])

    const filtered = leads.filter(lead => {
        const matchSearch = search === '' ||
            (lead.nomeCliente || '').toLowerCase().includes(search.toLowerCase()) ||
            (lead['nome da empresa'] || '').toLowerCase().includes(search.toLowerCase())
        const matchStatus = statusFilter === '' || lead.status === statusFilter
        return matchSearch && matchStatus
    })

    const formatDate = (dateStr: string) => {
        if (!dateStr) return '-'
        return new Date(dateStr).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Clientes</h2>
                    <p className="text-sm text-muted-foreground mt-1">{leads.length} cliente{leads.length !== 1 ? 's' : ''} cadastrado{leads.length !== 1 ? 's' : ''}</p>
                </div>
                <div className="flex items-center space-x-2">
                    <select
                        className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={statusFilter}
                        onChange={e => setStatusFilter(e.target.value)}
                    >
                        <option value="">Todos os status</option>
                        {Object.entries(STATUS_CONFIG).map(([key, val]) => (
                            <option key={key} value={key}>{val.label}</option>
                        ))}
                    </select>
                    <div className="relative">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <input
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring pl-8 w-[250px]"
                            placeholder="Buscar cliente..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                        />
                    </div>
                </div>
            </div>

            <Card>
                <CardContent className="p-0">
                    <div className="relative w-full overflow-auto">
                        <table className="w-full caption-bottom text-sm">
                            <thead className="[&_tr]:border-b">
                                <tr className="border-b transition-colors hover:bg-muted/50">
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Score</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Nome</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Empresa</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Nicho</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Telefone</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Última interação</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Status</th>
                                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">Ações</th>
                                </tr>
                            </thead>
                            <tbody className="[&_tr:last-child]:border-0">
                                {loading ? (
                                    <tr><td colSpan={8} className="text-center p-8 text-muted-foreground">Carregando...</td></tr>
                                ) : filtered.length === 0 ? (
                                    <tr><td colSpan={8} className="text-center p-8 text-muted-foreground">Nenhum cliente encontrado.</td></tr>
                                ) : filtered.map((lead) => {
                                    const statusCfg = STATUS_CONFIG[lead.status] || STATUS_CONFIG['active']
                                    return (
                                        <tr key={lead.id} className="border-b transition-colors hover:bg-muted/50">
                                            <td className="p-4 align-middle">
                                                <ScoreBar score={lead.lead_score ?? 0} />
                                            </td>
                                            <td className="p-4 align-middle font-medium">{lead.nomeCliente || '-'}</td>
                                            <td className="p-4 align-middle text-muted-foreground">{lead['nome da empresa'] || '-'}</td>
                                            <td className="p-4 align-middle">{lead.nicho_trabalho || 'N/A'}</td>
                                            <td className="p-4 align-middle text-muted-foreground">{lead.telefone || '-'}</td>
                                            <td className="p-4 align-middle text-muted-foreground text-xs">{formatDate(lead.last_interaction_at || lead.created_at)}</td>
                                            <td className="p-4 align-middle">
                                                <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusCfg.color}`}>
                                                    {statusCfg.label}
                                                </span>
                                            </td>
                                            <td className="p-4 align-middle text-right">
                                                <div className="flex justify-end gap-1">
                                                    <button className="p-2 hover:bg-accent rounded-md" title="WhatsApp">
                                                        <MessageCircle className="h-4 w-4 text-green-600" />
                                                    </button>
                                                    <button className="p-2 hover:bg-accent rounded-md" title="Ligar">
                                                        <Phone className="h-4 w-4" />
                                                    </button>
                                                    <button className="p-2 hover:bg-accent rounded-md" title="E-mail">
                                                        <Mail className="h-4 w-4" />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}

import { useState, useEffect } from 'react'
import axios from 'axios'
import { Card, CardContent } from "@/components/ui/card"
import { Search, Filter, Phone, Mail } from "lucide-react"

export default function LeadsPage() {
    const [leads, setLeads] = useState<any[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        axios.get('/api/dashboard/leads')
            .then(res => {
                setLeads(res.data)
                setLoading(false)
            })
            .catch(console.error)
    }, [])

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold tracking-tight">Leads</h2>
                <div className="flex items-center space-x-2">
                    <button className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2">
                        <Filter className="mr-2 h-4 w-4" />
                        Filter
                    </button>
                    <div className="relative">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <input className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 pl-8 w-[250px]" placeholder="Search leads..." />
                    </div>
                </div>
            </div>

            <Card>
                <CardContent className="p-0">
                    <div className="relative w-full overflow-auto">
                        <table className="w-full caption-bottom text-sm">
                            <thead className="[&_tr]:border-b">
                                <tr className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Score</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Nome</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Empresa</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Nicho</th>
                                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">Status</th>
                                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="[&_tr:last-child]:border-0">
                                {loading ? (
                                    <tr><td colSpan={6} className="text-center p-4">Loading...</td></tr>
                                ) : leads.map((lead) => (
                                    <tr key={lead.id} className="border-b transition-colors hover:bg-muted/50">
                                        <td className="p-4 align-middle font-bold text-lg">
                                            <span className={
                                                lead.lead_score >= 75 ? "text-red-500" :
                                                    lead.lead_score >= 50 ? "text-yellow-500" : "text-blue-500"
                                            }>
                                                {lead.lead_score}
                                            </span>
                                        </td>
                                        <td className="p-4 align-middle font-medium">{lead.nomeCliente}</td>
                                        <td className="p-4 align-middle text-muted-foreground">{lead["nome da empresa"] || "-"}</td>
                                        <td className="p-4 align-middle">{lead.nicho_trabalho || "N/A"}</td>
                                        <td className="p-4 align-middle">
                                            <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80">
                                                Active
                                            </span>
                                        </td>
                                        <td className="p-4 align-middle text-right">
                                            <div className="flex justify-end gap-2">
                                                <button className="p-2 hover:bg-accent rounded-md" title="WhatsApp">
                                                    <Phone className="h-4 w-4" />
                                                </button>
                                                <button className="p-2 hover:bg-accent rounded-md" title="Email">
                                                    <Mail className="h-4 w-4" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}

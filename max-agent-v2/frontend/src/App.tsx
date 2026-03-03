import { useState, useEffect } from 'react'
import axios from 'axios'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Card } from "@/components/ui/card"
import { Users, Calendar as CalendarIcon, DollarSign, Activity, LayoutDashboard, Settings } from "lucide-react"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

// Pages
import LeadsPage from '@/pages/LeadsPage'
import CalendarPage from '@/pages/CalendarPage'

// Dashboard Home Component
function DashboardHome() {
    const [kpis, setKpis] = useState<any>(null)
    const [funnelData, setFunnelData] = useState<any[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        Promise.all([
            axios.get('/api/dashboard/kpis'),
            axios.get('/api/dashboard/funnel')
        ]).then(([kpiRes, funnelRes]) => {
            setKpis(kpiRes.data)
            setFunnelData(funnelRes.data)
            setLoading(false)
        }).catch(err => {
            console.error(err)
            setLoading(false)
        })
    }, [])

    if (loading) return <div className="p-8">Loading Overview...</div>

    return (
        <div className="space-y-6">
            <h2 className="text-2xl font-bold tracking-tight">Overview</h2>
            {/* KPI Grid */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <KpiCard
                    title="Total Leads"
                    value={kpis?.total_leads || 0}
                    icon={<Users className="h-4 w-4 text-muted-foreground" />}
                    desc="+3 from last month"
                />
                <KpiCard
                    title="Monthly Appointments"
                    value={kpis?.monthly_appointments || 0}
                    icon={<CalendarIcon className="h-4 w-4 text-muted-foreground" />}
                    desc="4 upcoming"
                />
                <KpiCard
                    title="Conversion Rate"
                    value={kpis?.conversion_rate || "0%"}
                    icon={<Activity className="h-4 w-4 text-muted-foreground" />}
                    desc="+2% increase"
                />
                <KpiCard
                    title="Est. Revenue"
                    value={`R$ ${kpis?.estimated_revenue || 0}`}
                    icon={<DollarSign className="h-4 w-4 text-muted-foreground" />}
                    desc="Based on hot leads"
                />
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4">
                    <div className="p-6">
                        <h3 className="text-lg font-medium">Sales Funnel</h3>
                        <div className="h-[200px] mt-4">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={funnelData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                    <XAxis type="number" hide />
                                    <YAxis dataKey="name" type="category" width={100} tick={{ fontSize: 12 }} />
                                    <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                                    <Bar dataKey="value" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={20} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </Card>
                <Card className="col-span-3">
                    <div className="p-6">
                        <h3 className="text-lg font-medium">Recent Activity</h3>
                        <div className="mt-4 space-y-4">
                            <div className="flex items-center">
                                <div className="ml-4 space-y-1">
                                    <p className="text-sm font-medium leading-none">New Lead: John Doe</p>
                                    <p className="text-sm text-muted-foreground">High Score (85)</p>
                                </div>
                                <div className="ml-auto font-medium text-xs text-muted-foreground">2m ago</div>
                            </div>
                            <div className="flex items-center">
                                <div className="ml-4 space-y-1">
                                    <p className="text-sm font-medium leading-none">Appointment Scheduled</p>
                                    <p className="text-sm text-muted-foreground">Maria Silva - 14:00</p>
                                </div>
                                <div className="ml-auto font-medium text-xs text-muted-foreground">1h ago</div>
                            </div>
                        </div>
                    </div>
                </Card>
            </div>
        </div>
    )
}

function KpiCard({ title, value, icon, desc }: any) {
    return (
        <div className="rounded-xl border bg-card text-card-foreground shadow">
            <div className="p-6 flex flex-row items-center justify-between space-y-0 pb-2">
                <h3 className="tracking-tight text-sm font-medium">{title}</h3>
                {icon}
            </div>
            <div className="p-6 pt-0">
                <div className="text-2xl font-bold">{value}</div>
                <p className="text-xs text-muted-foreground">{desc}</p>
            </div>
        </div>
    )
}

function SidebarLink({ to, icon, label }: any) {
    const location = useLocation()
    const isActive = location.pathname === to

    return (
        <Link to={to} className={`flex items-center gap-3 rounded-lg px-3 py-2 transition-all hover:text-primary ${isActive ? "bg-muted text-primary" : "text-muted-foreground"}`}>
            {icon}
            {label}
        </Link>
    )
}

function Layout() {
    return (
        <div className="grid min-h-screen w-full md:grid-cols-[220px_1fr] lg:grid-cols-[280px_1fr]">
            <div className="hidden border-r bg-muted/40 md:block">
                <div className="flex h-full max-h-screen flex-col gap-2">
                    <div className="flex h-14 items-center border-b px-4 lg:h-[60px] lg:px-6">
                        <Link to="/" className="flex items-center gap-2 font-semibold">
                            <span className="">MAX Admin</span>
                        </Link>
                    </div>
                    <div className="flex-1">
                        <nav className="grid items-start px-2 text-sm font-medium lg:px-4 mt-4">
                            <SidebarLink to="/" icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
                            <SidebarLink to="/leads" icon={<Users className="h-4 w-4" />} label="Leads" />
                            <SidebarLink to="/calendar" icon={<CalendarIcon className="h-4 w-4" />} label="Calendar" />
                            <SidebarLink to="/settings" icon={<Settings className="h-4 w-4" />} label="Settings" />
                        </nav>
                    </div>
                </div>
            </div>
            <div className="flex flex-col">
                <header className="flex h-14 items-center gap-4 border-b bg-muted/40 px-4 lg:h-[60px] lg:px-6">
                    <div className="w-full flex-1">
                        {/* Header Content */}
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="h-8 w-8 rounded-full bg-secondary"></div>
                    </div>
                </header>
                <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-6">
                    <Routes>
                        <Route path="/" element={<DashboardHome />} />
                        <Route path="/leads" element={<LeadsPage />} />
                        <Route path="/calendar" element={<CalendarPage />} />
                        <Route path="/settings" element={<div className="p-8">Settings Page (Coming Soon)</div>} />
                    </Routes>
                </main>
            </div>
        </div>
    )
}

export default function App() {
    return (
        <Router>
            <Layout />
        </Router>
    )
}

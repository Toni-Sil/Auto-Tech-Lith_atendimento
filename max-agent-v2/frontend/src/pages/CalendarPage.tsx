import { useState, useEffect } from 'react'
import axios from 'axios'
import { Card } from "@/components/ui/card"
import { ChevronLeft, ChevronRight, Clock, Plus, CalendarDays } from "lucide-react"

const PT_DAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
const PT_MONTHS = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

export default function AgendaPage() {
    const [appointments, setAppointments] = useState<any[]>([])
    const [currentDate, setCurrentDate] = useState(new Date())

    useEffect(() => {
        axios.get('/api/dashboard/appointments')
            .then(res => setAppointments(res.data))
            .catch(console.error)
    }, [])

    const weekDays = Array.from({ length: 5 }, (_, i) => {
        // Seg a Sex da semana atual
        const day = new Date(currentDate)
        const dayOfWeek = day.getDay() // 0=Dom
        const monday = new Date(day)
        monday.setDate(day.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        const d = new Date(monday)
        d.setDate(monday.getDate() + i)
        return d
    })

    const hours = Array.from({ length: 10 }, (_, i) => i + 8) // 08:00 às 17:00

    const prevWeek = () => {
        const d = new Date(currentDate)
        d.setDate(d.getDate() - 7)
        setCurrentDate(d)
    }

    const nextWeek = () => {
        const d = new Date(currentDate)
        d.setDate(d.getDate() + 7)
        setCurrentDate(d)
    }

    const monthLabel = `${PT_MONTHS[weekDays[0]?.getMonth()]} ${weekDays[0]?.getFullYear()}`

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Agenda</h2>
                    <p className="text-sm text-muted-foreground mt-1">{appointments.length} agendamento{appointments.length !== 1 ? 's' : ''} encontrado{appointments.length !== 1 ? 's' : ''}</p>
                </div>
                <div className="flex items-center space-x-3">
                    <div className="flex items-center space-x-1">
                        <button onClick={prevWeek} className="p-2 border rounded hover:bg-accent">
                            <ChevronLeft className="h-4 w-4" />
                        </button>
                        <span className="font-semibold px-2 min-w-[160px] text-center">{monthLabel}</span>
                        <button onClick={nextWeek} className="p-2 border rounded hover:bg-accent">
                            <ChevronRight className="h-4 w-4" />
                        </button>
                    </div>
                    <button className="inline-flex items-center gap-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 text-sm font-medium">
                        <Plus className="h-4 w-4" />
                        Nova Agenda
                    </button>
                </div>
            </div>

            <Card className="overflow-hidden">
                <div className="grid border-b" style={{ gridTemplateColumns: '80px repeat(5, 1fr)' }}>
                    <div className="p-3 border-r bg-muted/50 font-medium text-xs text-muted-foreground text-center flex items-center justify-center">
                        <Clock className="h-3 w-3" />
                    </div>
                    {weekDays.map((day, idx) => {
                        const isToday = day.toDateString() === new Date().toDateString()
                        return (
                            <div key={idx} className={`p-3 border-r font-medium text-sm text-center ${
                                isToday ? 'bg-primary/10 text-primary' : 'bg-muted/20'
                            }`}>
                                <div className="text-xs text-muted-foreground">{PT_DAYS[day.getDay()]}</div>
                                <div className={`text-lg font-bold mt-0.5 ${ isToday ? 'text-primary' : '' }`}>
                                    {day.getDate()}
                                </div>
                            </div>
                        )
                    })}
                </div>

                <div className="max-h-[600px] overflow-y-auto">
                    {hours.map(hour => (
                        <div key={hour} className="border-b" style={{ display: 'grid', gridTemplateColumns: '80px repeat(5, 1fr)', minHeight: '80px' }}>
                            <div className="p-2 border-r text-xs text-muted-foreground text-center bg-muted/30 flex items-start justify-center pt-3">
                                {String(hour).padStart(2, '0')}:00
                            </div>
                            {weekDays.map((day, idx) => (
                                <div key={idx} className="border-r relative p-1 group hover:bg-accent/10 transition-colors">
                                    {appointments
                                        .filter(appt => {
                                            const d = new Date(appt.data_hora)
                                            return (
                                                d.getDate() === day.getDate() &&
                                                d.getMonth() === day.getMonth() &&
                                                d.getHours() === hour
                                            )
                                        })
                                        .map((appt, i) => {
                                            const d = new Date(appt.data_hora)
                                            return (
                                                <div key={i} className="absolute inset-1 bg-primary text-primary-foreground text-xs p-1.5 rounded-md overflow-hidden cursor-pointer hover:scale-[1.02] transition-transform z-10 shadow-sm">
                                                    <div className="font-bold truncate">{appt.nome_cliente || 'Cliente'}</div>
                                                    {appt.tipo && <div className="text-[10px] opacity-80 truncate">{appt.tipo}</div>}
                                                    <div className="text-[10px] opacity-75 flex items-center gap-1 mt-0.5">
                                                        <Clock className="w-2.5 h-2.5" />
                                                        {String(d.getHours()).padStart(2,'0')}:{String(d.getMinutes()).padStart(2,'0')}
                                                    </div>
                                                </div>
                                            )
                                        })
                                    }
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    )
}

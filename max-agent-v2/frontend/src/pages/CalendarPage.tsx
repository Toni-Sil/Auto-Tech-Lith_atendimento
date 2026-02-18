import { useState, useEffect } from 'react'
import axios from 'axios'
import { Card } from "@/components/ui/card"
import { ChevronLeft, ChevronRight, Clock } from "lucide-react"

export default function CalendarPage() {
    const [appointments, setAppointments] = useState<any[]>([])

    useEffect(() => {
        axios.get('/api/dashboard/appointments')
            .then(res => setAppointments(res.data))
            .catch(console.error)
    }, [])

    const days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    const hours = Array.from({ length: 10 }, (_, i) => i + 9) // 9 to 18

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold tracking-tight">Calendar</h2>
                <div className="flex items-center space-x-2">
                    <button className="p-2 border rounded hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
                    <span className="font-semibold">February 2026</span>
                    <button className="p-2 border rounded hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
                </div>
            </div>

            <Card className="overflow-hidden">
                <div className="grid grid-cols-6 border-b">
                    <div className="p-4 border-r bg-muted/50 font-medium text-sm text-muted-foreground text-center">Time</div>
                    {days.map(day => (
                        <div key={day} className="p-4 border-r font-medium text-sm text-center bg-muted/20">
                            {day}
                        </div>
                    ))}
                </div>
                <div className="max-h-[600px] overflow-y-auto">
                    {hours.map(hour => (
                        <div key={hour} className="grid grid-cols-6 h-20 border-b">
                            <div className="p-2 border-r text-xs text-muted-foreground text-center bg-muted/50">
                                {hour}:00
                            </div>
                            {days.map((day, idx) => (
                                <div key={`${day}-${hour}`} className="border-r relative p-1 group hover:bg-accent/10 transition-colors">
                                    {/* Mocking placement logic */}
                                    {appointments.map((appt, i) => {
                                        // Simple mock check: if appt time matches roughly
                                        // Real logic requires strict Date parsing
                                        const apptDate = new Date(appt.data_hora)
                                        const apptDay = apptDate.getDay() - 1 // Mon=0
                                        const apptHour = apptDate.getHours()

                                        if (apptDay === idx && apptHour === hour) {
                                            return (
                                                <div key={i} className="absolute inset-1 bg-primary text-primary-foreground text-xs p-1 rounded overflow-hidden cursor-pointer hover:scale-105 transition-transform z-10 shadow-sm">
                                                    <div className="font-bold truncate">{appt.nome_cliente || "Cliente"}</div>
                                                    <div className="truncate opacity-90 text-[10px] flex items-center">
                                                        <Clock className="w-3 h-3 mr-1" /> {apptDate.getMinutes() === 0 ? "00" : apptDate.getMinutes()}
                                                    </div>
                                                </div>
                                            )
                                        }
                                        return null
                                    })}
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    )
}

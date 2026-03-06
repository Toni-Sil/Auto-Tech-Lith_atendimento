from flask import Flask, render_template
from app.infrastructure.database.supabase_client import SupabaseClient
from app.config.settings import get_settings
import os

settings = get_settings()

app = Flask(__name__, 
            template_folder=os.path.abspath("app/api/admin/templates"),
            static_folder=os.path.abspath("app/api/admin/static"))
app.secret_key = settings.admin_secret_key

@app.route('/')
def index():
    return "Admin Panel is Running. Go to <a href='/leads'>/leads</a>"

@app.route('/leads')
def leads_dashboard():
    supabase = SupabaseClient.get_client()
    
    # Busca leads com score > 0 (ou todos)
    response = supabase.table("customers").select("*").order("lead_score", desc=True).execute()
    leads = response.data if response.data else []
    
    return render_template('dashboard.html', leads=leads)

@app.route('/funnel')
def funnel_dashboard():
    from app.services.analytics_service import AnalyticsService
    service = AnalyticsService()
    
    # 30 days is default
    metrics = service.get_funnel_metrics(days=30)
    insights = service.generate_insights(metrics)
    
    return render_template('funnel.html', metrics=metrics, insights=insights)

if __name__ == '__main__':
    app.run(port=settings.admin_port, debug=settings.debug)

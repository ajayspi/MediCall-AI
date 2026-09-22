"use client";

import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export default function DashboardPage() {
  const [stats, setStats] = useState({
    callsToday: 0,
    revenueToday: 0,
    successRate: 0,
    avgResponse: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        // TODO: Replace with actual Supabase queries
        const mockStats = {
          callsToday: 47,
          revenueToday: 4820,
          successRate: 94,
          avgResponse: 487,
        };
        setStats(mockStats);
      } catch (err) {
        console.error("Failed to fetch stats:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 mt-1">Welcome back! Here's what's happening today.</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          label="Calls Today"
          value={stats.callsToday}
          trend="+8 from 7-day avg"
          trendUp={true}
          icon={<PhoneIcon />}
        />
        <KPICard
          label="Revenue Today"
          value={`$${stats.revenueToday.toLocaleString()}`}
          trend="+12% vs yesterday"
          trendUp={true}
          icon={<DollarIcon />}
        />
        <KPICard
          label="Order Success Rate"
          value={`${stats.successRate}%`}
          trend="+2pp this week"
          trendUp={true}
          icon={<CheckIcon />}
        />
        <KPICard
          label="Avg Response"
          value={`${stats.avgResponse}ms`}
          trend="Deepgram + GPT-4.1"
          trendUp={false}
          icon={<ClockIcon />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Today's Call Volume" subtitle="Hourly breakdown">
          <CallVolumeChart />
        </Card>
        <Card title="Peak Hours Distribution" subtitle="When calls come in">
          <PeakHoursChart />
        </Card>
      </div>

      {/* Recent Orders */}
      <Card title="Recent Orders" subtitle="Latest activity" action={<Link href="/orders" className="text-sm font-medium text-primary-400 hover:underline">View all →</Link>}>
        <RecentOrdersTable />
      </Card>
    </div>
  );
}

function KPICard({ label, value, trend, trendUp, icon }: { label: string; value: string; trend: string; trendUp: boolean; icon: React.ReactNode }) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-slate-400">{label}</span>
        <div className="w-10 h-10 rounded-xl bg-primary-500/20 flex items-center justify-center text-primary-400">
          {icon}
        </div>
      </div>
      <div className="text-3xl font-black text-white mb-2">{value}</div>
      <div className={`flex items-center gap-1 text-sm ${trendUp ? 'text-green-400' : 'text-slate-500'}`}>
        <span className="font-medium">{trendUp ? '↑' : '—'}</span>
        <span>{trend}</span>
      </div>
    </div>
  );
}

function Card({ title, subtitle, children, action }: { title: string; subtitle: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <p className="text-sm text-slate-400">{subtitle}</p>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function CallVolumeChart() {
  return (
    <div className="h-64 flex items-end justify-around px-4">
      {Array.from({ length: 24 }, (_, i) => {
        const height = Math.max(20, Math.random() * 180);
        const isPeak = i >= 11 && i <= 14 || i >= 18 && i <= 21;
        return (
          <div key={i} className="flex-1 flex flex-col items-center">
            <div
              className={`w-full rounded-t transition-all duration-300 ${
                isPeak ? 'bg-gradient-to-t from-primary-500 to-primary-400' : 'bg-slate-700/50'
              }`}
              style={{ height: `${height}px` }}
            />
            <span className="text-xs text-slate-500 mt-2">{i}:00</span>
          </div>
        );
      })}
    </div>
  );
}

function PeakHoursChart() {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  return (
    <div className="h-64 flex items-end justify-around px-4">
      {days.map((day, i) => {
        const height = Math.max(20, Math.random() * 180);
        return (
          <div key={day} className="flex-1 flex flex-col items-center">
            <div className="w-full rounded-t bg-gradient-to-t from-purple-500 to-pink-500" style={{ height: `${height}px` }} />
            <span className="text-xs text-slate-500 mt-2">{day}</span>
          </div>
        );
      })}
    </div>
  );
}

function RecentOrdersTable() {
  const mockOrders = [
    { id: "ORD-001", customer: "+61 2 8941 2345", items: "Large Margherita, Garlic Bread", total: "$32.50", state: "PAID", time: "09:41" },
    { id: "ORD-002", customer: "+61 3 9876 5432", items: "Chicken Parma, Chips", total: "$28.00", state: "LINK_SENT", time: "09:35" },
    { id: "ORD-003", customer: "+61 7 3321 9876", items: "2x Pepperoni, Coke", total: "$41.20", state: "SYNCED", time: "09:28" },
    { id: "ORD-004", customer: "+61 8 8234 5678", items: "Margherita, Garlic Bread, Coke", total: "$35.50", state: "PLACED", time: "09:22" },
    { id: "ORD-005", customer: "+61 2 8941 1122", items: "Hawaiian, Diet Coke", total: "$29.80", state: "PAID", time: "09:15" },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="text-left text-sm text-slate-500 border-b border-white/10">
            <th className="pb-3 font-medium">Order</th>
            <th className="pb-3 font-medium">Customer</th>
            <th className="pb-3 font-medium">Items</th>
            <th className="pb-3 font-medium">Total</th>
            <th className="pb-3 font-medium">State</th>
            <th className="pb-3 font-medium">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {mockOrders.map((order) => (
            <tr key={order.id} className="hover:bg-white/[0.02]">
              <td className="py-4 font-mono text-sm">{order.id}</td>
              <td className="py-4 text-sm">{order.customer}</td>
              <td className="py-4 text-sm text-slate-300 max-w-xs truncate">{order.items}</td>
              <td className="py-4 font-medium">{order.total}</td>
              <td className="py-4">
                <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                  order.state === 'PAID' ? 'bg-green-500/20 text-green-400' :
                  order.state === 'LINK_SENT' ? 'bg-yellow-500/20 text-yellow-400' :
                  order.state === 'SYNCED' ? 'bg-blue-500/20 text-blue-400' :
                  'bg-slate-500/20 text-slate-400'
                }`}>
                  {order.state}
                </span>
              </td>
              <td className="py-4 text-sm text-slate-500">{order.time}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Icons
function PhoneIcon() {
  return <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13 2.257a1 1 0 011.21-.502l4.493-1.498a1 1 0 01.684-.949h1.078a2 2 0 002-2V7a2 2 0 00-2-2h-.095a1 1 0 01-.948-.684l-1.498-4.493a1 1 0 01.502-1.21l2.257-1.13a11.042 11.042 0 00-5.516-5.516l-1.13-2.257a1 1 0 01-1.21.502l-4.493 1.498a1 1 0 01-.684.949H3a2 2 0 00-2 2v.095z" /></svg>;
}

function DollarIcon() {
  return <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.105 0 2-.895 2-2 0-.5-.17-.96-.485-1.374a4.001 4.001 0 00-.91-1.892 4 4 0 00-1.553-.72m1.98 12.158c.316.3.6.583.882.85.223.265.477.486.749.67a10.319 10.319 0 003.176 1.47c.669.176 1.342.194 2.007.06a4.26 4.26 0 001.826-2.55 4.431 4.431 0 00-.474-2.31c-.136-.304-.256-.605-.357-.895M12 3v2.25M12 16.5V21" /></svg>;
}

function CheckIcon() {
  return <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}

function ClockIcon() {
  return <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
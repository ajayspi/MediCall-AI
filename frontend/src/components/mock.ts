// Mock data for the clinic + admin dashboard shells (dashboards phase).
// The API-routes phase replaces this with live backend data. Indian medical
// context: +91 numbers, rupee revenue, 5 languages (hi/en/ta/te/bn),
// Exotel/Knowlarity/Twilio-India telephony, Razorpay/PhonePe/Cashfree.

export type MockCall = {
  id: string;
  caller: string;
  language: string;
  state: string;
  severity: string;
  duration: string;
  complaint: string;
  startedAt: string;
};

// ---- Clinic shells -------------------------------------------------------

export const clinicKpis = [
  { label: "Calls Today", value: "47", trend: "+8 vs 7-day avg", trendUp: true },
  { label: "Active Calls", value: "4", trend: "2 in triage", trendUp: true },
  { label: "Appointments Today", value: "12", trend: "9 confirmed", trendUp: true },
  { label: "Avg Pickup", value: "0:08", trend: "Deepgram STT · 5 languages", trendUp: true },
];

export const todayCalls: MockCall[] = [
  { id: "C-1042", caller: "+91 98450 12345", language: "hi", state: "COMPLETE", severity: "green", duration: "03:12", complaint: "Fever and body ache follow-up", startedAt: "09:41" },
  { id: "C-1041", caller: "+91 98860 22331", language: "ta", state: "TRIAGE", severity: "amber", duration: "02:47", complaint: "Chest discomfort, mild", startedAt: "09:38" },
  { id: "C-1040", caller: "+91 90040 88721", language: "en", state: "APPOINTMENT", severity: "green", duration: "01:55", complaint: "Booking diabetic checkup", startedAt: "09:31" },
  { id: "C-1039", caller: "+91 99630 41092", language: "te", state: "PRESCRIPTION", severity: "amber", duration: "04:02", complaint: "Refill hypertension meds", startedAt: "09:22" },
  { id: "C-1038", caller: "+91 70030 55678", language: "bn", state: "COMPLETE", severity: "green", duration: "02:38", complaint: "Vaccination slot enquiry", startedAt: "09:15" },
];

export const liveCallKpis = [
  { label: "Active Calls", value: "4", trend: "2 in triage", trendUp: true },
  { label: "On Hold", value: "1", trend: "waiting for doctor", trendUp: true },
  { label: "Escalated", value: "1", trend: "EMS notified", trendUp: false },
  { label: "Avg Duration", value: "4:12", trend: "healthy pipeline", trendUp: true },
];

export const triageQueue = [
  { id: "C-1041", caller: "+91 98860 22331", language: "ta", complaint: "Chest discomfort, mild", severity: "amber", waiting: "04:12" },
  { id: "C-1039", caller: "+91 99630 41092", language: "te", complaint: "Refill hypertension meds", severity: "amber", waiting: "03:48" },
  { id: "C-1045", caller: "+91 91234 77890", language: "hi", complaint: "High fever since 2 days", severity: "red", waiting: "02:31" },
  { id: "C-1046", caller: "+91 98390 11223", language: "en", complaint: "Persistent headache", severity: "amber", waiting: "01:58" },
  { id: "C-1047", caller: "+91 99950 33210", language: "ta", complaint: "Child vomiting, mild", severity: "green", waiting: "01:05" },
  { id: "C-1048", caller: "+91 70540 90123", language: "bn", complaint: "BP reading question", severity: "green", waiting: "00:42" },
];

export const appointmentKpis = [
  { label: "Today's Appointments", value: "12", trend: "9 confirmed", trendUp: true },
  { label: "Pending Confirmation", value: "2", trend: "SMS pending", trendUp: true },
  { label: "Completed", value: "5", trend: "on track", trendUp: true },
  { label: "No-shows", value: "1", trend: "reminder sent", trendUp: false },
];

export const appointments = [
  { time: "09:30", patient: "Ramesh Iyer", doctor: "Dr. A. Nair", reason: "Diabetes follow-up", status: "Completed" },
  { time: "10:00", patient: "Fatima Begum", doctor: "Dr. S. Rao", reason: "Antenatal checkup", status: "Confirmed" },
  { time: "10:30", patient: "K. Venkatesh", doctor: "Dr. A. Nair", reason: "Hypertension review", status: "Confirmed" },
  { time: "11:00", patient: "Priya Sharma", doctor: "Dr. M. Khan", reason: "Thyroid panel", status: "Pending" },
  { time: "11:30", patient: "Abdul Rahman", doctor: "Dr. S. Rao", reason: "Wound dressing", status: "Confirmed" },
  { time: "12:00", patient: "Lakshmi Devi", doctor: "Dr. M. Khan", reason: "Ortho consult", status: "No-show" },
];

export const prescriptionKpis = [
  { label: "Issued Today", value: "8", trend: "via voice agent", trendUp: true },
  { label: "Renewals", value: "3", trend: "refill requests", trendUp: true },
  { label: "Pending Approval", value: "2", trend: "doctor review", trendUp: false },
];

export const prescriptions = [
  { patient: "Ramesh Iyer", medicine: "Metformin 500mg", dosage: "1-0-1", frequency: "After meals", doctor: "Dr. A. Nair", status: "Active" },
  { patient: "Fatima Begum", medicine: "Iron + Folic Acid", dosage: "0-0-1", frequency: "Night", doctor: "Dr. S. Rao", status: "Active" },
  { patient: "K. Venkatesh", medicine: "Amlodipine 5mg", dosage: "0-0-1", frequency: "Night", doctor: "Dr. A. Nair", status: "Renewal" },
  { patient: "Priya Sharma", medicine: "Thyroxine 50mcg", dosage: "1-0-0", frequency: "Empty stomach", doctor: "Dr. M. Khan", status: "Pending" },
  { patient: "Abdul Rahman", medicine: "Amoxicillin 500mg", dosage: "1-1-1", frequency: "8-hourly", doctor: "Dr. S. Rao", status: "Active" },
];

export const patientKpis = [
  { label: "Total Patients", value: "1,284", trend: "+36 this month", trendUp: true },
  { label: "Repeat Callers", value: "71%", trend: "retention strong", trendUp: true },
  { label: "Languages Served", value: "5", trend: "hi · en · ta · te · bn", trendUp: true },
];

export const patients = [
  { name: "Ramesh Iyer", phone: "+91 98450 12345", language: "ta", lastVisit: "12 Sep 2026", calls: 9 },
  { name: "Priya Sharma", phone: "+91 91234 66778", language: "hi", lastVisit: "18 Sep 2026", calls: 4 },
  { name: "Abdul Rahman", phone: "+91 98390 88776", language: "en", lastVisit: "20 Sep 2026", calls: 6 },
  { name: "Lakshmi Devi", phone: "+91 99630 44123", language: "te", lastVisit: "02 Sep 2026", calls: 3 },
  { name: "Fatima Begum", phone: "+91 70030 55678", language: "bn", lastVisit: "Today", calls: 2 },
  { name: "K. Venkatesh", phone: "+91 90040 99887", language: "ta", lastVisit: "15 Sep 2026", calls: 11 },
];

export const analyticsKpis = [
  { label: "Calls Today", value: "47", trend: "+8 vs 7-day avg", trendUp: true },
  { label: "Avg Duration", value: "4:12", trend: "steady", trendUp: true },
  { label: "Resolution Rate", value: "92%", trend: "+3pp this week", trendUp: true },
  { label: "Escalation Rate", value: "4%", trend: "below 5% target", trendUp: true },
];

export const hourlyCalls = [
  2, 1, 1, 0, 2, 4, 6, 9, 12, 14, 11, 13, 16, 18, 15, 12, 14, 17, 19, 14, 10, 7, 5, 3,
];

export const languageMix = [
  { lang: "hi", pct: 46, label: "हिन्दी" },
  { lang: "en", pct: 28, label: "English" },
  { lang: "ta", pct: 14, label: "தமிழ்" },
  { lang: "te", pct: 8, label: "తెలుగు" },
  { lang: "bn", pct: 4, label: "বাংলা" },
];

export const severityMix = [
  { severity: "green", pct: 64, label: "Green" },
  { severity: "amber", pct: 28, label: "Amber" },
  { severity: "red", pct: 6, label: "Red" },
  { severity: "critical", pct: 2, label: "Critical" },
];

// ---- Admin shells --------------------------------------------------------

export const adminKpis = [
  { label: "Active Clinics", value: "8", trend: "+2 this quarter", trendUp: true },
  { label: "Calls Today", value: "1,247", trend: "across all clinics", trendUp: true },
  { label: "Live Calls", value: "37", trend: "3 providers in use", trendUp: true },
  { label: "Revenue Today", value: "₹1,24,500", trend: "+9% vs yesterday", trendUp: true },
];

export const platformClinics = [
  { name: "City Care Clinic", city: "Chennai", plan: "Growth", status: "Active", callsMtd: 1840, seats: 12 },
  { name: "Apollo Family Care", city: "Hyderabad", plan: "Enterprise", status: "Active", callsMtd: 2960, seats: 24 },
  { name: "Nightingale Clinic", city: "Kolkata", plan: "Starter", status: "Active", callsMtd: 610, seats: 4 },
  { name: "Shifa Health Centre", city: "Lucknow", plan: "Growth", status: "Active", callsMtd: 1210, seats: 10 },
  { name: "Green Valley Hospital", city: "Bengaluru", plan: "Enterprise", status: "Trial", callsMtd: 442, seats: 8 },
  { name: "Sunrise Polyclinic", city: "Pune", plan: "Starter", status: "Paused", callsMtd: 0, seats: 3 },
];

export const doctorList = [
  { name: "Dr. A. Nair", specialty: "General Medicine", clinic: "City Care Clinic", languages: "hi · en · ta", status: "Active" },
  { name: "Dr. S. Rao", specialty: "OB-GYN", clinic: "City Care Clinic", languages: "en · te", status: "Active" },
  { name: "Dr. M. Khan", specialty: "Cardiology", clinic: "City Care Clinic", languages: "hi · ur", status: "Active" },
  { name: "Dr. P. Das", specialty: "Pediatrics", clinic: "Nightingale Clinic", languages: "bn · en", status: "Active" },
  { name: "Dr. R. Reddy", specialty: "Orthopedics", clinic: "Apollo Family Care", languages: "te · en", status: "On leave" },
  { name: "Dr. J. Thomas", specialty: "Dermatology", clinic: "Shifa Health Centre", languages: "en · hi", status: "Active" },
];

export const platformPatients = [
  { name: "Ramesh Iyer", phone: "+91 98450 12345", clinic: "City Care Clinic", language: "ta", lastActivity: "09:41 today" },
  { name: "K. Venkatesh", phone: "+91 90040 99887", clinic: "City Care Clinic", language: "ta", lastActivity: "Yesterday" },
  { name: "Mohammed Asif", phone: "+91 99630 11223", clinic: "Shifa Health Centre", language: "hi", lastActivity: "Yesterday" },
  { name: "Sandra D'Souza", phone: "+91 98860 44556", clinic: "Green Valley Hospital", language: "en", lastActivity: "2 days ago" },
  { name: "Rupali Sen", phone: "+91 70030 77889", clinic: "Nightingale Clinic", language: "bn", lastActivity: "3 days ago" },
];

export const revenueKpis = [
  { label: "Revenue Today", value: "₹1,24,500", trend: "+9% vs yesterday", trendUp: true },
  { label: "Revenue MTD", value: "₹18,42,300", trend: "91% of monthly target", trendUp: true },
  { label: "Collection Rate", value: "96%", trend: "gateways healthy", trendUp: true },
  { label: "Pending Invoices", value: "3", trend: "₹28,400 due", trendUp: false },
];

export const gateways = [
  { name: "Razorpay", status: "healthy", txns: 142, share: "54%" },
  { name: "PhonePe", status: "healthy", txns: 88, share: "33%" },
  { name: "Cashfree", status: "degraded", txns: 34, share: "13%" },
];

export const invoices = [
  { id: "INV-2041", clinic: "City Care Clinic", amount: "₹8,400", gateway: "Razorpay", status: "Paid" },
  { id: "INV-2042", clinic: "Apollo Family Care", amount: "₹12,000", gateway: "PhonePe", status: "Paid" },
  { id: "INV-2043", clinic: "Shifa Health Centre", amount: "₹7,200", gateway: "Cashfree", status: "Pending" },
  { id: "INV-2044", clinic: "Nightingale Clinic", amount: "₹4,800", gateway: "Razorpay", status: "Paid" },
  { id: "INV-2045", clinic: "Green Valley Hospital", amount: "₹16,400", gateway: "PhonePe", status: "Pending" },
];

export const plans = [
  { name: "Starter", price: "₹2,999/mo", seats: "Up to 5", details: "1 language pair, 500 call mins" },
  { name: "Growth", price: "₹6,999/mo", seats: "Up to 15", details: "5 languages, unlimited mins" },
  { name: "Enterprise", price: "Custom", seats: "Unlimited", details: "Dedicated number pool + SLA" },
];

export const clinicBills = [
  { clinic: "City Care Clinic", plan: "Growth", amount: "₹6,999", cycle: "01 Oct 2026", status: "Paid" },
  { clinic: "Apollo Family Care", plan: "Enterprise", amount: "₹24,000", cycle: "01 Oct 2026", status: "Paid" },
  { clinic: "Nightingale Clinic", plan: "Starter", amount: "₹2,999", cycle: "01 Oct 2026", status: "Paid" },
  { clinic: "Shifa Health Centre", plan: "Growth", amount: "₹6,999", cycle: "01 Oct 2026", status: "Due" },
  { clinic: "Green Valley Hospital", plan: "Enterprise", amount: "₹24,000", cycle: "01 Oct 2026", status: "Trial" },
];

export const infrastructure = [
  { name: "Exotel", role: "Telephony (primary)", status: "up", latency: "42ms", note: "All numbers operational" },
  { name: "Knowlarity", role: "Telephony (fallback)", status: "up", latency: "51ms", note: "SR API healthy" },
  { name: "Twilio India", role: "Telephony (fallback)", status: "up", latency: "48ms", note: "STMS routed IND" },
  { name: "LiveKit", role: "Voice rooms", status: "up", latency: "38ms", note: "37 active rooms" },
  { name: "Deepgram", role: "STT · 5 languages", status: "up", latency: "210ms", note: "hi/en/ta/te/bn configured" },
  { name: "ElevenLabs", role: "TTS", status: "up", latency: "180ms", note: "Per-language voices" },
  { name: "OpenAI", role: "Agent brain", status: "up", latency: "610ms", note: "Model healthy" },
  { name: "PostgreSQL", role: "Primary data", status: "up", latency: "9ms", note: "P95 query < 40ms" },
  { name: "Redis", role: "Session cache", status: "degraded", latency: "14ms", note: "Eviction pressure — plan scale-up" },
];

export const auditLog = [
  { time: "09:44", actor: "v.anand@medicall.ai", action: "Replayed call webhook", target: "Call C-1042", ip: "103.42.9.18" },
  { time: "09:12", actor: "platform-admin", action: "Created clinic", target: "Green Valley Hospital", ip: "49.207.42.101" },
  { time: "08:57", actor: "s.rao@citycare.in", action: "Approved prescription", target: "Rx #8821", ip: "152.58.17.64" },
  { time: "08:40", actor: "platform-admin", action: "Upgraded plan", target: "Apollo Family Care → Enterprise", ip: "49.207.42.101" },
  { time: "07:55", actor: "k.iyer@citycare.in", action: "Granted dashboard access", target: "Dr. M. Khan", ip: "152.58.17.64" },
  { time: "07:31", actor: "system", action: "Rotated gateway key", target: "Cashfree", ip: "internal" },
];
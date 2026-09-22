import Link from "next/link";

const TALKBYTE_LOGO = (
  <svg width="45" height="45" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style={{ stopColor: "#7c3aed", stopOpacity: 1 }} />
        <stop offset="100%" style={{ stopColor: "#14b8a6", stopOpacity: 1 }} />
      </linearGradient>
    </defs>
    <rect x="40" y="25" width="20" height="30" rx="10" fill="url(#logoGradient)" />
    <line x1="50" y1="55" x2="50" y2="75" stroke="url(#logoGradient)" strokeWidth="3" strokeLinecap="round" />
    <line x1="35" y1="75" x2="65" y2="75" stroke="url(#logoGradient)" strokeWidth="3" strokeLinecap="round" />
    <path d="M 20 40 Q 15 50 20 60" stroke="#7c3aed" strokeWidth="2.5" fill="none" opacity="0.7" />
    <path d="M 10 35 Q 3 50 10 65" stroke="#7c3aed" strokeWidth="2" fill="none" opacity="0.5" />
    <path d="M 80 40 Q 85 50 80 60" stroke="#14b8a6" strokeWidth="2.5" fill="none" opacity="0.7" />
    <path d="M 90 35 Q 97 50 90 65" stroke="#14b8a6" strokeWidth="2" fill="none" opacity="0.5" />
  </svg>
);

export default function Home() {
  return (
    <main className="flex flex-col">
      {/* Hero Section */}
      <section className="relative min-h-[90vh] flex items-center justify-center px-6 py-20">
        <div className="absolute inset-0 bg-gradient-to-b from-primary-500/10 via-transparent to-transparent" />
        <div className="max-w-7xl mx-auto w-full text-center">
          <div className="inline-flex px-3 py-1 rounded-full bg-primary-500/20 text-primary-400 text-xs font-bold uppercase tracking-wider mb-8">
            AI Voice · Australia
          </div>
          
          <div className="flex items-center justify-center gap-2 mb-6">
            {TALKBYTE_LOGO}
            <span className="text-2xl font-bold text-white tracking-tight">TalkByte</span>
          </div>

          <h1 className="max-w-5xl text-5xl sm:text-7xl lg:text-8xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-white to-white/60 pb-2 drop-shadow-sm">
            AI Phone Ordering
            <br className="hidden sm:block" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-400 via-purple-400 to-blue-500 animate-gradient-x">
              Every Call. Every Order. Answered.
            </span>
          </h1>

          <p className="mt-8 max-w-2xl mx-auto text-lg sm:text-xl text-slate-300 leading-relaxed font-light">
            TalkByte's voice AI answers your restaurant's phone, takes orders naturally, 
            syncs with Square, and never sleeps — even at 2am on a Friday night.
          </p>

          <div className="mt-12 flex flex-col sm:flex-row gap-5 items-center justify-center">
            <Link href="/signup" className="btn-primary group">
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2 13h20" />
              </svg>
              Start Free 14-Day Trial
            </Link>
            <Link href="/demo" className="btn-secondary">
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Watch Demo
            </Link>
          </div>
        </div>

        {/* Stats Ticker */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-wrap justify-center gap-8 sm:gap-16 text-center opacity-60 animate-fade-in-up">
          <div className="flex flex-col items-center">
            <div className="text-3xl font-black text-white mb-1">487</div>
            <div className="text-xs text-slate-400">Restaurants</div>
          </div>
          <div className="flex flex-col items-center">
            <div className="text-3xl font-black text-white mb-1">99.4%</div>
            <div className="text-xs text-slate-400">Accuracy</div>
          </div>
          <div className="flex flex-col items-center">
            <div className="text-3xl font-black text-white mb-1">487ms</div>
            <div className="text-xs text-slate-400">Latency</div>
          </div>
          <div className="flex flex-col items-center">
            <div className="text-3xl font-black text-white mb-1">$0</div>
            <div className="text-xs text-slate-400">Missed Revenue</div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-24 px-6 bg-slate-900/50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Built for Australian Kitchens
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto text-lg">
              Six reasons 487 restaurants trust TalkByte to answer their phones.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature) => (
              <div key={feature.title} className="card p-8 group">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary-500/20 to-purple-500/20 flex items-center justify-center mb-6 text-primary ring-1 ring-primary-500/30 group-hover:ring-primary-500/50 transition-all">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={feature.icon} />
                  </svg>
                </div>
                <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
                <p className="text-slate-300 leading-relaxed">{feature.description}</p>
                <div className="mt-6 text-primary-400 font-bold text-sm tracking-wider uppercase">
                  {feature.metric}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Call Journey */}
      <section className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              The Call Journey
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto text-lg">
              Ring to receipt in 487ms
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {callJourney.map((step, index) => (
              <div key={step.title} className="relative">
                <div className="aspect-[9/16] rounded-3xl bg-slate-800/50 border border-white/10 overflow-hidden">
                  <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
                    <div className="text-center">
                      <div className="text-5xl font-black text-white mb-2">{index + 1}</div>
                      <h3 className="text-xl font-bold text-white mb-2">{step.title}</h3>
                      <p className="text-slate-400">{step.description}</p>
                      <div className="mt-4 inline-flex px-3 py-1 rounded-full bg-primary-500/20 text-primary-400 text-xs font-bold uppercase tracking-wider">
                        {step.tech}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Live Demo */}
      <section className="py-24 px-6 bg-slate-900/50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Live Demo
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto text-lg">
              Hear a real call — your AI sounds exactly like this, trained on thousands of Australian restaurant calls.
            </p>
          </div>

          <div className="rounded-3xl bg-black/50 border border-white/10 overflow-hidden">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
                <span className="font-medium">Active Call</span>
                <span className="text-slate-500 text-sm">+61 2 8941 ···</span>
              </div>
              <div className="flex items-center gap-2 text-slate-500 text-sm">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6l4 2" />
                </svg>
                00:00
              </div>
            </div>
            
            <div className="p-6 space-y-4 max-h-[400px] overflow-y-auto">
              {demoConversation.map((msg) => (
                <div key={msg.id} className={`flex ${msg.from === 'ai' ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                    msg.from === 'ai' 
                      ? 'bg-primary-500/20 border border-primary-500/30 text-slate-100' 
                      : 'bg-slate-700 border border-white/10 text-slate-200'
                  }`}>
                    <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
                      <span>{msg.from === 'ai' ? '🎙️ AI' : '📞 Customer'}</span>
                      <span className="text-slate-500">{msg.time}</span>
                    </div>
                    <p className="text-base">{msg.text}</p>
                  </div>
                </div>
              ))}
            </div>
            
            <div className="p-6 border-t border-white/10 grid grid-cols-4 gap-4">
              <div className="text-center p-4 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="text-2xl font-black text-white">47</div>
                <div className="text-xs text-slate-500">Calls Today</div>
              </div>
              <div className="text-center p-4 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="text-2xl font-black text-white">94%</div>
                <div className="text-xs text-slate-500">Order Success</div>
              </div>
              <div className="text-center p-4 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="text-2xl font-black text-white">$4,820</div>
                <div className="text-xs text-slate-500">Revenue Today</div>
              </div>
              <div className="text-center p-4 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="text-2xl font-black text-white">487ms</div>
                <div className="text-xs text-slate-500">Avg Response</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Global Expansion */}
      <section className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Global Expansion
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto text-lg">
              One codebase. Every market.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {expansionMarkets.map((market) => (
              <div key={market.country} className="card p-8 relative">
                <div className="absolute top-6 right-6 text-5xl font-black text-white/5">{market.flag}</div>
                <div className="inline-flex px-3 py-1 rounded-full bg-primary-500/20 text-primary-400 text-xs font-bold uppercase tracking-wider mb-4">
                  {market.status}
                </div>
                <h3 className="text-2xl font-bold mb-2">{market.country} {market.name}</h3>
                <p className="text-slate-400 mb-6">{market.description}</p>
                <div className="flex flex-wrap gap-2">
                  {market.tech.map((t) => (
                    <span key={t} className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-xs text-slate-400">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Beyond Restaurants */}
      <section className="py-24 px-6 bg-slate-900/50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Beyond Restaurants
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto text-lg">
              Any voice-first ordering vertical plugs straight in.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {verticals.map((v) => (
              <div key={v.title} className="card p-8">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary-500/20 to-purple-500/20 flex items-center justify-center mb-6 text-primary ring-1 ring-primary-500/30">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={v.icon} />
                  </svg>
                </div>
                <h3 className="text-xl font-bold mb-3">{v.title}</h3>
                <p className="text-slate-300">{v.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Pricing
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto text-lg">
              Simple. Honest. All plans include unlimited AI minutes, Square sync, and Australian support.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {pricing.map((plan) => (
              <div key={plan.name} className={`card p-8 relative ${plan.popular ? 'ring-2 ring-primary-500/50' : ''}`}>
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex px-3 py-1 rounded-full bg-primary-500 text-primary-900 text-xs font-bold uppercase tracking-wider">
                    Most Popular
                  </div>
                )}
                <h3 className="text-xl font-bold mb-2">{plan.name}</h3>
                <div className="mb-6">
                  <span className="text-4xl font-black text-white">${plan.price}</span>
                  <span className="text-slate-500">/month · {plan.locations}</span>
                </div>
                <ul className="space-y-4 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-3 text-slate-300">
                      <svg className="w-5 h-5 text-primary-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link 
                  href={plan.cta.href} 
                  className={`w-full py-4 rounded-full text-base font-bold text-center transition-all ${
                    plan.popular 
                      ? 'bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-xl shadow-primary-500/20 hover:scale-105' 
                      : 'border border-white/20 bg-white/5 backdrop-blur-md text-white hover:bg-white/10'
                  }`}
                >
                  {plan.cta.text}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Footer */}
      <section className="py-24 px-6 bg-gradient-to-b from-primary-500/10 to-transparent">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 font-bold text-xl tracking-tight text-white/50 mb-6">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2 13h20" />
            </svg>
            TalkByte
          </div>
          <h2 className="text-4xl md:text-6xl font-black mb-6">
            Your restaurant <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-400 to-purple-400">misses calls.</span>
          </h2>
          <p className="text-xl text-slate-300 mb-10 max-w-2xl mx-auto">
            Every missed call is a missed order. TalkByte answers every one.
          </p>
          <Link href="/signup" className="btn-primary inline-block">
            Start Free 14-Day Trial →
          </Link>
          <p className="mt-6 text-sm text-slate-500">
            Setup in 15 min · No credit card · Australian support
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 bg-black/50 py-12">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-white/50">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2 13h20" />
            </svg>
            TalkByte
          </div>
          <p className="text-sm text-slate-400">© 2026 TalkByte · Built for Australian restaurants</p>
          <div className="flex gap-4 text-sm font-medium text-slate-400">
            <span>LiveKit</span>
            <span>·</span>
            <span>Deepgram</span>
            <span>·</span>
            <span>GPT-4.1</span>
            <span>·</span>
            <span>ElevenLabs</span>
            <span>·</span>
            <span>Telnyx</span>
            <span>·</span>
            <span>Square</span>
            <span>·</span>
            <span>Stripe</span>
          </div>
        </div>
      </footer>
    </main>
  );
}

const features = [
  {
    title: "Natural Voice AI",
    description: "Deepgram STT + GPT-4.1 + ElevenLabs TTS. Understands accents, specials, and Australian slang. Sounds genuinely human.",
    icon: "M12 14l4-4M15 11c.83 0 1.5-.67 1.5-1.5S15.83 8 15 8s-1.5.67-1.5 1.5S13.17 11 15 11zM3.055 11H5a8 8 0 0116 0h2.945M12 14c-3.52 0-6.564 2.14-7.6 5.2M12 14l4-4",
    metric: "487ms end-to-end latency",
    title: "Natural Voice AI",
  },
  {
    title: "Square POS Sync",
    description: "Orders appear in Square the moment they're confirmed. Menu prices and availability sync automatically. Zero double-entry.",
    icon: "M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z",
    metric: "Live two-way sync",
    title: "Square POS Sync",
  },
  {
    title: "Never Miss a Call",
    description: "Peak hours, holidays, 2am cravings — handled without extra staff.",
    icon: "M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0112 21c-2.5 0-4.847-.675-7-1.984z",
    metric: "24/7 Always On",
    title: "Never Miss a Call",
  },
  {
    title: "Phone Payments",
    description: "Stripe-powered card payments over the phone. PCI-compliant, instant settlement.",
    icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z",
    metric: "PCI-compliant",
    title: "Phone Payments",
  },
  {
    title: "Live Dashboard",
    description: "Real-time call monitoring, revenue tracking, sentiment analysis.",
    icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 002 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h2a2 2 0 012 2v10a2 2 0 01-2 2h-2a2 2 0 01-2-2zm0 0V9a2 2 0 012-2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h2a2 2 0 002 2v2a2 2 0 002 2h2a2 2 0 012 2v6a2 2 0 01-2 2H8a2 2 0 01-2-2z",
    metric: "Real-time monitoring",
    title: "Live Dashboard",
  },
  {
    title: "Expansion Architecture",
    description: "Backend is a plug-in system. Each market/vertical needs: POS adapter, payment gateway, language model, phone numbers. AI pipeline is market-agnostic.",
    icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10",
    metric: "~2 weeks per POS adapter",
    title: "Expansion Architecture",
  },
];

const callJourney = [
  { title: "Phone Rings", description: "Customer calls your Telnyx number", tech: "Telnyx" },
  { title: "AI Greets", description: "LiveKit agent picks up, speaks naturally", tech: "LiveKit + ElevenLabs" },
  { title: "Order Taken", description: "GPT-4.1 handles items, mods, upsells", tech: "Deepgram + GPT-4.1" },
  { title: "SMS Sent", description: "Confirmation to customer instantly", tech: "Telnyx SMS" },
  { title: "POS Synced", description: "Order fires to Square. Kitchen prints.", tech: "Square + Stripe" },
];

const demoConversation = [
  { id: 1, from: 'ai', text: "Hi! Welcome to Mama's Pizzeria. What can I get you?", time: "9:41" },
  { id: 2, from: 'customer', text: "Large Margherita and garlic bread please.", time: "9:41" },
  { id: 3, from: 'ai', text: "One large Margherita, garlic bread! Anything else?", time: "9:42" },
  { id: 4, from: 'customer', text: "A Coke as well.", time: "9:42" },
  { id: 5, from: 'ai', text: "Perfect! That's $32.50 total. Confirming your order now!", time: "9:42" },
  { id: 6, from: 'ai', text: "Order confirmed! You'll receive an SMS with a payment link. Your food will be ready in 20 minutes.", time: "9:43" },
];

const expansionMarkets = [
  {
    country: "🇦🇺",
    name: "Australia — Live Today",
    status: "CURRENT MARKET",
    description: "487 restaurants live. Square POS, Stripe, Telnyx, English only.",
    tech: ["Square POS", "Stripe", "Telnyx", "English"],
    flag: "🇦🇺",
  },
  {
    country: "🇺🇸",
    name: "United States",
    status: "HIGH PRIORITY",
    description: "Same stack. Swap Telnyx numbers to US DIDs, add Toast/Clover POS adapters, enable Spanish-English bilingual mode. 1M+ restaurants TAM.",
    tech: ["Toast POS", "Clover", "en+es"],
    flag: "🇺🇸",
  },
  {
    country: "🇬🇧",
    name: "United Kingdom",
    status: "HIGH PRIORITY",
    description: "Near-zero integration delta. UK English voice model, Lightspeed/Tevalis POS connectors. Strong takeaway culture makes this a day-one win.",
    tech: ["Lightspeed", "Tevalis", "UK English"],
    flag: "🇬🇧",
  },
  {
    country: "🇮🇳",
    name: "India",
    status: "GROWTH",
    description: "Hindi + 6 regional languages via Deepgram multilingual. Petpooja / Posist POS. Fastest-growing restaurant market in Asia-Pacific.",
    tech: ["Petpooja", "Posist", "Hindi+6 langs"],
    flag: "🇮🇳",
  },
  {
    country: "🇨🇦",
    name: "Canada",
    status: "GROWTH",
    description: "EN + FR bilingual mandate. Square already works. Moneris payment gateway swap. Highly aligned regulatory environment.",
    tech: ["Square", "Moneris", "EN+FR"],
    flag: "🇨🇦",
  },
  {
    country: "🇳🇿",
    name: "New Zealand",
    status: "GROWTH",
    description: "Identical stack to AU. Same Square POS support. ~18,000 restaurants. Essentially a free expansion from AU operations.",
    tech: ["Square", "Stripe", "Telnyx"],
    flag: "🇳🇿",
  },
];

const verticals = [
  {
    title: "Taxi & Rideshare",
    description: "AI dispatches bookings over phone. Same LiveKit pipeline, swap the order logic for trip scheduling.",
    icon: "M18.931 5c.91 0 1.643.781 1.548 1.685l-1.486 9.36A2 2 0 0118.92 21H5.08a2 2 0 01-1.897-2.276L3.05 6.685A2 2 0 014.54 5h15.46z",
  },
  {
    title: "Salons & Spas",
    description: "Appointment booking, cancellations, upsells. Integrates with Mindbody / Fresha via webhook adapter.",
    icon: "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z",
  },
  {
    title: "Medical Clinics",
    description: "HIPAA-grade call handling. Appointment booking, prescription refill triage, after-hours routing.",
    icon: "M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-7.682 7.682zm0 0l7.682 7.682M12 21h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v12a2 2 0 002 2z",
  },
  {
    title: "Grocery & FMCG",
    description: "Phone-in grocery orders for elderly / accessibility demographics. Connects to any inventory API.",
    icon: "M16 11V7a4 4 0 11-8 0v4m0 0l-3 3m4-4l3 3m-3.5-3.5L6.75 14.25M18 11l-3 3m4-4l3 3m-3.5-3.5l-3.25 3.25",
  },
  {
    title: "Hotels & Hospitality",
    description: "Room service, concierge requests, reservation management. Connects to Opera / Cloudbeds PMS.",
    icon: "M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z",
  },
  {
    title: "B2B Ordering",
    description: "Wholesale trade ordering by phone. Catches orders that would have gone to voicemail or a sales rep.",
    icon: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
  },
];

const pricing = [
  {
    name: "Starter",
    price: 149,
    locations: "1 location",
    popular: false,
    features: [
      "Unlimited AI calls",
      "Square POS sync",
      "SMS confirmations",
      "Restaurant dashboard",
    ],
    cta: { text: "Get Started", href: "/signup?plan=starter" },
  },
  {
    name: "Growth",
    price: 199,
    locations: "3 locations",
    popular: true,
    features: [
      "Everything in Starter",
      "Up to 3 locations",
      "Stripe phone payments",
      "Analytics & reporting",
    ],
    cta: { text: "Start Free Trial", href: "/signup?plan=growth" },
  },
  {
    name: "Enterprise",
    price: 299,
    locations: "unlimited",
    popular: false,
    features: [
      "Everything in Growth",
      "Unlimited locations",
      "Custom voice & script",
      "Dedicated AM",
    ],
    cta: { text: "Contact Sales", href: "/contact?plan=enterprise" },
  },
];

export { features, callJourney, demoConversation, expansionMarkets, verticals, pricing };
import { Link } from 'react-router-dom';

export default function LandingPage() {
  return (
    <main className="landing-page flex-1 w-full px-5 sm:px-8">
      <header className="mx-auto flex w-full max-w-7xl items-center justify-between border-b border-slate-800/80 py-5">
        <Link to="/" aria-label="Conan home" className="inline-flex items-center gap-3 text-slate-100">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-sky-400/20 bg-sky-400/10 text-sky-300">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path d="M12 3v18M5 7h14M7 7l-4 9h8L7 7Zm10 0-4 9h8l-4-9ZM5 21h14" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="text-base font-semibold tracking-tight">Conan</span>
        </Link>
        <span className="hidden sm:inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Contract intelligence
        </span>
      </header>

      <section className="mx-auto grid w-full max-w-7xl items-center gap-14 py-16 sm:py-24 lg:grid-cols-[1.1fr_.9fr] lg:gap-20 lg:py-32">
        <div className="max-w-2xl">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-sky-400/20 bg-sky-400/[0.07] px-3.5 py-1.5 text-xs font-medium text-sky-200">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-300" /> AI contract obligation &amp; risk intelligence
          </div>
          <h1 className="mb-6 max-w-2xl text-4xl font-semibold leading-[1.08] tracking-[-0.045em] text-white sm:text-5xl lg:text-6xl">
            From clauses to consequences.
          </h1>
          <p className="mb-9 max-w-xl text-base leading-7 text-slate-400 sm:text-lg">
            Turn complex agreements into a clear view of obligations, deadlines, dependencies, and potential inconsistencies.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Link to="/upload" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-sky-300 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-sky-950/30 transition hover:bg-sky-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-200">
              Upload Contract
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </Link>
            <Link to="/upload" className="inline-flex min-h-12 items-center justify-center rounded-lg border border-slate-700 bg-slate-900/70 px-5 py-3 text-sm font-medium text-slate-200 transition hover:border-slate-600 hover:bg-slate-800">
              Try Sample Contract
            </Link>
          </div>
          <p className="mt-5 text-xs text-slate-500">PDF analysis · Clear source evidence · Review-ready outputs</p>
        </div>

        <div className="relative mx-auto w-full max-w-lg lg:mx-0 lg:justify-self-end">
          <div className="absolute -inset-8 rounded-[2rem] bg-sky-500/[0.07] blur-3xl" />
          <div className="relative overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-900/90 p-6 shadow-2xl shadow-black/30 sm:p-8">
            <div className="mb-7 flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-sky-400/20 bg-sky-400/10 text-sky-300">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M7 3h7l5 5v13H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm7 0v5h5M9 13h6m-6 4h6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </span>
              <div><p className="text-sm font-semibold text-slate-100">A clearer view of every agreement</p><p className="mt-1 text-xs text-slate-500">One connected contract workspace</p></div>
            </div>
            <div className="space-y-3">
              {[
                ['01', 'Obligations', 'Understand who needs to do what'],
                ['02', 'Evidence', 'Trace findings back to contract language'],
                ['03', 'Dependencies', 'See how milestones relate'],
                ['04', 'Review', 'Keep people in control of decisions'],
              ].map(([step, title, detail], index) => (
                <div key={step} className="relative flex items-center gap-4 rounded-xl border border-slate-800 bg-slate-950/55 p-4">
                  {index < 3 && <span className="absolute -bottom-3 left-[2.15rem] z-10 h-3 border-l border-slate-700" />}
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 font-mono text-[10px] text-sky-200">{step}</span>
                  <div className="min-w-0"><p className="text-xs font-semibold text-slate-200">{title}</p><p className="mt-1 text-[11px] leading-4 text-slate-500">{detail}</p></div>
                </div>
              ))}
            </div>
            <div className="mt-6 flex items-center gap-2 border-t border-slate-800 pt-5 text-[11px] text-slate-500"><svg className="h-3.5 w-3.5 text-emerald-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M10 1.7a.75.75 0 0 1 .36.09l6 3.1a.75.75 0 0 1 .4.67v4.28c0 3.7-2.5 6.87-6.14 7.78a.75.75 0 0 1-.36 0C6.62 16.7 4.12 13.53 4.12 9.84V5.56a.75.75 0 0 1 .4-.67l6-3.1A.75.75 0 0 1 10 1.7Z" clipRule="evenodd" /></svg> Evidence-led insights, with human review in control</div>
          </div>
        </div>
      </section>

      <footer className="mx-auto flex w-full max-w-7xl flex-col gap-2 border-t border-slate-800/80 py-5 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <span>Conan · AI contract obligation &amp; risk intelligence</span>
        <span>From clauses to consequences.</span>
      </footer>
    </main>
  );
}

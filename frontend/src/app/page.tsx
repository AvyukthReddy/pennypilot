export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
          PennyPilot
        </h1>
        <p className="max-w-md text-lg text-zinc-600 dark:text-zinc-400">
          AI Financial Copilot — Phase 0 foundation is up and running.
        </p>
      </main>
    </div>
  );
}

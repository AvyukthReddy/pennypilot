const bars = [40, 65, 30, 80, 55, 90, 70];

const transactions = [
  { label: "Whole Foods", category: "Groceries", amount: "-$64.20" },
  { label: "Spotify", category: "Subscriptions", amount: "-$11.99" },
  { label: "Paycheck", category: "Income", amount: "+$2,150.00" },
];

export function DashboardPreview() {
  return (
    <div
      aria-hidden
      className="mx-auto w-full max-w-sm rounded-2xl border-2 border-black bg-white p-5 text-left shadow-[6px_6px_0_0_#000] dark:border-zinc-50 dark:bg-zinc-950 dark:shadow-[6px_6px_0_0_#fafafa]"
    >
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Total balance</p>
          <p className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
            $4,281.09
          </p>
        </div>
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
          +2.4% this month
        </span>
      </div>

      <div className="mb-5 flex h-16 items-end gap-1.5">
        {bars.map((height, i) => (
          <div
            key={i}
            className={
              height === Math.max(...bars)
                ? "flex-1 rounded-t-sm bg-yellow-300"
                : "flex-1 rounded-t-sm bg-black dark:bg-zinc-50"
            }
            style={{ height: `${height}%` }}
          />
        ))}
      </div>

      <ul className="space-y-3">
        {transactions.map((tx) => (
          <li key={tx.label} className="flex items-center justify-between text-sm">
            <div>
              <p className="font-medium text-black dark:text-zinc-50">{tx.label}</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">{tx.category}</p>
            </div>
            <span
              className={
                tx.amount.startsWith("+")
                  ? "font-medium text-emerald-600 dark:text-emerald-400"
                  : "font-medium text-zinc-700 dark:text-zinc-300"
              }
            >
              {tx.amount}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

import type { ReactNode } from "react";

export function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="group rounded-2xl border-2 border-black bg-white p-6 transition hover:-translate-y-1 hover:shadow-[6px_6px_0_0_#000] dark:border-zinc-50 dark:bg-zinc-950 dark:hover:shadow-[6px_6px_0_0_#fafafa]">
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-black text-zinc-50 transition group-hover:bg-yellow-300 group-hover:text-black dark:bg-zinc-50 dark:text-black dark:group-hover:bg-yellow-300">
        {icon}
      </div>
      <h3 className="mb-1.5 text-base font-semibold text-black dark:text-zinc-50">{title}</h3>
      <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{description}</p>
    </div>
  );
}

import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { DashboardPreview } from "@/components/dashboard-preview";
import { FeatureCard } from "@/components/feature-card";
import {
  ChartIcon,
  ChatIcon,
  ConnectIcon,
  ReceiptIcon,
  SparkleIcon,
  TrendIcon,
} from "@/components/icons";

const features = [
  {
    icon: <ConnectIcon className="h-5 w-5" />,
    title: "Connect your accounts",
    description:
      "Securely link your bank accounts and see every transaction across all of them in one place.",
  },
  {
    icon: <ReceiptIcon className="h-5 w-5" />,
    title: "Receipt & statement OCR",
    description:
      "Snap a photo or upload a statement — PennyPilot reads it, extracts the line items, and files it for you.",
  },
  {
    icon: <SparkleIcon className="h-5 w-5" />,
    title: "AI categorization",
    description:
      "Every transaction is automatically tagged and categorized, so you never have to sort spending by hand.",
  },
  {
    icon: <ChartIcon className="h-5 w-5" />,
    title: "Budgeting insights",
    description:
      "See exactly where your money goes, with budgets that learn from your habits instead of fighting them.",
  },
  {
    icon: <TrendIcon className="h-5 w-5" />,
    title: "Forecasting & anomaly detection",
    description:
      "Know what next month looks like before it happens, and get flagged the moment something looks off.",
  },
  {
    icon: <ChatIcon className="h-5 w-5" />,
    title: "AI chat assistant",
    description:
      "Ask questions about your finances in plain English and get answers grounded in your own data, via RAG.",
  },
];

const steps = [
  {
    number: "01",
    title: "Connect",
    description:
      "Link your bank accounts, or upload statements and receipts directly.",
  },
  {
    number: "02",
    title: "Understand",
    description:
      "AI categorizes every transaction and builds a live picture of your spending.",
  },
  {
    number: "03",
    title: "Act",
    description:
      "Get budgets, forecasts, and anomaly alerts — and ask your data anything.",
  },
];

export default async function Home() {
  const supabase = createClient(await cookies());
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    redirect("/home");
  }

  return (
    <div className="bg-zinc-50 font-sans dark:bg-black">
      {/* Hero */}
      <section className="relative isolate overflow-hidden border-b-2 border-black px-6 pt-20 pb-24 sm:pt-28 dark:border-zinc-50">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-black sm:text-5xl dark:text-zinc-50">
            Your money, <span className="bg-yellow-300 px-2 text-black">understood.</span>
          </h1>
          <p className="mt-4 max-w-xl text-lg text-zinc-600 dark:text-zinc-400">
            PennyPilot is an AI financial copilot — it connects your accounts,
            reads your receipts, and turns raw transactions into budgets,
            forecasts, and answers.
          </p>

          <div className="mt-8 flex gap-3">
            <Link
              href="/signup"
              className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
            >
              Get started
            </Link>
            <Link
              href="/login"
              className="rounded-md border-2 border-black px-4 py-2 text-sm font-medium text-black hover:bg-black hover:text-white dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black"
            >
              Sign in
            </Link>
          </div>

          <div className="mt-16 w-full">
            <DashboardPreview />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-black sm:text-3xl dark:text-zinc-50">
            Everything your money needs, in one copilot
          </h2>
          <p className="mt-3 text-zinc-600 dark:text-zinc-400">
            From connecting accounts to answering questions about your spending
            — PennyPilot handles the busywork so you can focus on decisions.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <FeatureCard key={feature.title} {...feature} />
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="border-t-2 border-black bg-white px-6 py-24 dark:border-zinc-50 dark:bg-zinc-950">
        <div className="mx-auto max-w-5xl">
          <div className="mx-auto mb-14 max-w-2xl text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-black sm:text-3xl dark:text-zinc-50">
              How it works
            </h2>
          </div>

          <div className="relative grid grid-cols-1 gap-10 sm:grid-cols-3">
            <div
              aria-hidden
              className="absolute top-6 right-0 left-0 hidden h-px bg-zinc-200 sm:block dark:bg-zinc-800"
            />
            {steps.map((step) => (
              <div
                key={step.number}
                className="relative flex flex-col items-center text-center"
              >
                <div className="relative z-10 mb-4 flex h-12 w-12 items-center justify-center rounded-full border-2 border-black bg-white text-sm font-semibold text-black dark:border-zinc-50 dark:bg-zinc-950 dark:text-zinc-50">
                  {step.number}
                </div>
                <h3 className="mb-1.5 text-base font-semibold text-black dark:text-zinc-50">
                  {step.title}
                </h3>
                <p className="max-w-xs text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="px-6 py-10 text-center text-xs text-zinc-500 dark:text-zinc-500">
        PennyPilot — AI Financial Copilot
      </footer>
    </div>
  );
}

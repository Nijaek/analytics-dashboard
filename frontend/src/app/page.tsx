import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-4">Analytics Dashboard</h1>
      <p className="text-gray-600 mb-8 text-center max-w-lg">
        Real-time event analytics platform. Track page views, user actions, and
        conversions across your sites and apps.
      </p>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition"
        >
          Sign In
        </Link>
        <Link
          href="/register"
          className="px-6 py-3 border border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition"
        >
          Create Account
        </Link>
      </div>
    </main>
  );
}

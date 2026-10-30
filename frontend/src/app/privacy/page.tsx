import Link from "next/link";

export const metadata = { title: "Privacy notice" };

// Plain-language summary of docs/SECURITY_AND_PRIVACY.md. Keep both in sync.
export default function PrivacyPage() {
  return (
    <main id="main" className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <Link href="/" className="text-navy-700 underline">← NyayaSetu</Link>
      <h1 className="text-3xl font-bold text-navy-900">Privacy notice</h1>
      <p>NyayaSetu handles sensitive legal and personal information. This notice explains what we store, why, and your choices.</p>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold text-navy-900">What we store</h2>
        <ul className="list-disc space-y-1 pl-6">
          <li>Your account details (name, email, optional phone) and preferences.</li>
          <li>The facts of your case that you give or confirm, so NyayaSetu can prepare documents.</li>
          <li>Conversation transcripts — only if you allow it.</li>
          <li>Documents you upload — only if you allow it. They are encrypted before storage.</li>
          <li>Voice recordings — only if you allow it. By default audio is converted to text and discarded.</li>
          <li>An audit log of important actions (for example approvals), without document contents.</li>
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold text-navy-900">External processing</h2>
        <p>
          If you allow &ldquo;external AI processing&rdquo;, parts of your conversation are sent to an AI provider (Anthropic)
          to understand your answers and phrase replies. If you use server speech recognition, audio is sent to Sarvam AI.
          Without these permissions NyayaSetu uses its built-in rules and your browser&apos;s own speech features.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold text-navy-900">Your rights</h2>
        <ul className="list-disc space-y-1 pl-6">
          <li>Change your consent choices at any time in Settings → Privacy.</li>
          <li>Download a copy of your data from Settings.</li>
          <li>Request deletion of your account and data; it is completed within 30 days.</li>
        </ul>
        <p>These controls are designed with India&apos;s Digital Personal Data Protection Act, 2023 in mind.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold text-navy-900">Not legal advice</h2>
        <p>NyayaSetu is not a lawyer or law firm. It never files, signs, pays or shares anything without your explicit approval.</p>
      </section>
    </main>
  );
}

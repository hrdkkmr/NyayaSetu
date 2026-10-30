"use client";

import {
  Accessibility, FileCheck2, FileText, Gavel, Landmark, Lock, MessageCircle, Mic, Phone, Scale, ShieldCheck, Smartphone,
  Type, Waypoints,
} from "lucide-react";
import Link from "next/link";

import { Footer, PublicHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { useI18n } from "@/lib/i18n";

export default function LandingPage() {
  const { t } = useI18n();
  const steps = [
    { icon: MessageCircle, title: t("landing.how1Title"), body: t("landing.how1Body") },
    { icon: Scale, title: t("landing.how2Title"), body: t("landing.how2Body") },
    { icon: FileText, title: t("landing.how3Title"), body: t("landing.how3Body") },
    { icon: Waypoints, title: t("landing.how4Title"), body: t("landing.how4Body") },
  ];
  return (
    <>
      <PublicHeader />
      <main id="main">
        <section className="bg-navy-900 text-white">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 md:grid-cols-[1.2fr_1fr] md:py-20">
            <div className="space-y-6">
              <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-sm">
                <Landmark className="size-4" aria-hidden /> {t("common.tagline")}
              </p>
              <h1 className="text-3xl font-bold leading-tight md:text-5xl">{t("landing.heroTitle")}</h1>
              <p className="max-w-xl text-lg text-navy-100">{t("landing.heroBody")}</p>
              <div className="flex flex-wrap gap-3">
                <Button asChild size="lg" className="bg-white text-navy-900 hover:bg-navy-50">
                  <Link href="/register"><Mic aria-hidden /> {t("landing.ctaStart")}</Link>
                </Button>
                <Button asChild size="lg" variant="secondary" className="border-white/60 bg-transparent text-white hover:bg-white/10">
                  <Link href="/login">{t("landing.ctaSignIn")}</Link>
                </Button>
              </div>
            </div>
            <Card className="self-center border-0 bg-white text-ink">
              <CardBody className="space-y-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-navy-800">
                  <Mic className="size-4" aria-hidden /> {t("landing.voiceTitle")}
                </p>
                <div className="space-y-3" aria-label="Example conversation">
                  <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-navy-100 px-4 py-2 text-navy-900">
                    {t("landing.voiceSample1")}
                  </p>
                  <p className="max-w-[85%] rounded-2xl rounded-bl-sm border border-line bg-canvas px-4 py-2">
                    {t("landing.voiceSample2")}
                  </p>
                </div>
                <div className="flex items-end justify-center gap-1 py-2" aria-hidden>
                  {[0.4, 0.8, 1, 0.6, 0.9, 0.5, 0.7].map((h, i) => (
                    <span key={i} className="w-1.5 rounded-full bg-navy-700" style={{ height: `${h * 28}px` }} />
                  ))}
                </div>
                <p className="text-sm text-muted">{t("landing.voiceBody")}</p>
              </CardBody>
            </Card>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-14">
          <h2 className="mb-8 text-2xl font-bold text-navy-900 md:text-3xl">{t("landing.howTitle")}</h2>
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(({ icon: Icon, title, body }, i) => (
              <li key={title}>
                <Card className="h-full">
                  <CardBody className="space-y-2">
                    <div className="flex items-center gap-3">
                      <span className="flex size-9 items-center justify-center rounded-full bg-navy-800 font-bold text-white">{i + 1}</span>
                      <Icon className="size-6 text-navy-700" aria-hidden />
                    </div>
                    <h3 className="text-lg font-semibold text-navy-900">{title}</h3>
                    <p className="text-muted">{body}</p>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ol>
        </section>

        <section className="bg-white py-14">
          <div className="mx-auto max-w-6xl px-4">
            <h2 className="mb-8 text-2xl font-bold text-navy-900 md:text-3xl">{t("landing.categoriesTitle")}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="border-navy-700">
                <CardBody className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="flex items-center gap-2 text-xl font-semibold text-navy-900"><FileCheck2 className="size-6" aria-hidden />{t("landing.catConsumer")}</h3>
                    <Badge tone="success">{t("landing.fullSupport")}</Badge>
                  </div>
                  <p className="text-muted">{t("landing.catConsumerBody")}</p>
                </CardBody>
              </Card>
              <Card>
                <CardBody className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="flex items-center gap-2 text-xl font-semibold text-navy-900"><Gavel className="size-6" aria-hidden />{t("landing.catOther")}</h3>
                    <Badge tone="info">{t("landing.comingSoon")}</Badge>
                  </div>
                  <p className="text-muted">{t("landing.catOtherBody")}</p>
                </CardBody>
              </Card>
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl gap-6 px-4 py-14 md:grid-cols-2">
          <Card>
            <CardBody className="space-y-4">
              <h2 className="flex items-center gap-2 text-xl font-bold text-navy-900"><Accessibility className="size-6" aria-hidden />{t("landing.accessTitle")}</h2>
              <ul className="space-y-3">
                {[
                  [MessageCircle, t("landing.access1")], [Mic, t("landing.access2")],
                  [Type, t("landing.access3")], [Smartphone, t("landing.access4")],
                ].map(([Icon, text]) => {
                  const I = Icon as typeof Mic;
                  return <li key={text as string} className="flex items-center gap-3"><I className="size-5 text-navy-700" aria-hidden />{text as string}</li>;
                })}
              </ul>
            </CardBody>
          </Card>
          <Card className="bg-saffron-100/40">
            <CardBody className="space-y-3">
              <h2 className="flex items-center gap-2 text-xl font-bold text-navy-900"><Phone className="size-6" aria-hidden />{t("landing.legalAidTitle")}</h2>
              <p>{t("landing.legalAidBody")}</p>
              <div className="flex flex-wrap gap-2">
                <a href="https://nalsa.gov.in/" target="_blank" rel="noopener noreferrer" className="font-semibold text-navy-700 underline">nalsa.gov.in</a>
                <a href="https://consumerhelpline.gov.in/" target="_blank" rel="noopener noreferrer" className="font-semibold text-navy-700 underline">consumerhelpline.gov.in</a>
              </div>
            </CardBody>
          </Card>
        </section>

        <section className="bg-navy-50 py-14">
          <div className="mx-auto max-w-6xl space-y-6 px-4">
            <h2 className="flex items-center gap-2 text-2xl font-bold text-navy-900"><ShieldCheck className="size-7" aria-hidden />{t("landing.trustTitle")}</h2>
            <ul className="grid gap-4 sm:grid-cols-2">
              {[t("landing.trust1"), t("landing.trust2"), t("landing.trust3"), t("landing.trust4")].map((text) => (
                <li key={text} className="flex gap-3 rounded-lg bg-white p-4"><Lock className="mt-0.5 size-5 shrink-0 text-navy-700" aria-hidden />{text}</li>
              ))}
            </ul>
            <div className="rounded-lg border-l-4 border-saffron-600 bg-white p-4">
              <p className="font-semibold text-navy-900">{t("landing.disclaimerTitle")}</p>
              <p className="text-muted">{t("landing.disclaimer")}</p>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

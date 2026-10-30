"use client";

import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as LabelPrimitive from "@radix-ui/react-label";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Check, CheckCircle2, Info, X, XCircle } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const fieldBase =
  "w-full rounded-lg border border-line bg-white px-3 text-base text-ink placeholder:text-muted/80 focus-visible:border-navy-700 disabled:bg-canvas aria-[invalid=true]:border-danger-700";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(fieldBase, "min-h-11", className)} {...props} />,
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(fieldBase, "min-h-24 py-2", className)} {...props} />,
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => <select ref={ref} className={cn(fieldBase, "min-h-11", className)} {...props} />,
);
Select.displayName = "Select";

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root ref={ref} className={cn("text-sm font-semibold text-ink", className)} {...props} />
));
Label.displayName = "Label";

export function Field({
  id, label, hint, error, children, className,
}: { id: string; label: React.ReactNode; hint?: React.ReactNode; error?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && !error && <p id={`${id}-hint`} className="text-sm text-muted">{hint}</p>}
      {error && <p id={`${id}-error`} role="alert" className="text-sm font-medium text-danger-700">{error}</p>}
    </div>
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-[var(--radius-card)] border border-line bg-surface shadow-sm", className)} {...props} />;
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold text-navy-900", className)} {...props} />;
}
export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", {
  variants: {
    tone: {
      neutral: "bg-canvas text-muted border border-line",
      info: "bg-navy-100 text-navy-800",
      success: "bg-success-100 text-success-700",
      warning: "bg-warning-100 text-warning-700",
      danger: "bg-danger-100 text-danger-700",
      accent: "bg-saffron-100 text-saffron-600",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

const alertIcons = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle };
const alertStyles = {
  info: "border-navy-100 bg-navy-50 text-navy-900",
  success: "border-success-100 bg-success-100 text-success-700",
  warning: "border-warning-100 bg-warning-100 text-warning-700",
  danger: "border-danger-100 bg-danger-100 text-danger-700",
};

export function Alert({
  tone = "info", title, children, className,
}: { tone?: keyof typeof alertStyles; title?: React.ReactNode; children?: React.ReactNode; className?: string }) {
  const Icon = alertIcons[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-lg border p-3 text-sm", alertStyles[tone], className)}>
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="leading-relaxed">{children}</div>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-line/60", className)} />;
}

export const Tabs = TabsPrimitive.Root;
export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn("flex w-full gap-1 overflow-x-auto border-b border-line [scrollbar-width:thin]", className)}
    {...props}
  />
));
TabsList.displayName = "TabsList";
export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "min-h-11 shrink-0 border-b-[3px] border-transparent px-3 text-sm font-semibold text-muted hover:text-navy-800 data-[state=active]:border-navy-700 data-[state=active]:text-navy-900",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";
export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => <TabsPrimitive.Content ref={ref} className={cn("pt-5", className)} {...props} />);
TabsContent.displayName = "TabsContent";

export const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      "mt-0.5 size-5 shrink-0 rounded border-2 border-navy-700 bg-white data-[state=checked]:bg-navy-800",
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator className="flex items-center justify-center text-white">
      <Check className="size-4" strokeWidth={3} />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
));
Checkbox.displayName = "Checkbox";

export const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full bg-line transition-colors data-[state=checked]:bg-navy-700",
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb className="block size-5 translate-x-1 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-6" />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  title, description, children, className,
}: { title: React.ReactNode; description?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-navy-950/50" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-white p-5 shadow-xl",
          className,
        )}
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <DialogPrimitive.Title className="text-lg font-semibold text-navy-900">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close className="rounded p-1 text-muted hover:bg-canvas" aria-label="Close">
            <X className="size-5" />
          </DialogPrimitive.Close>
        </div>
        {description && <DialogPrimitive.Description className="mb-4 text-sm text-muted">{description}</DialogPrimitive.Description>}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function EmptyState({
  icon: Icon, title, body, action,
}: { icon: React.ComponentType<{ className?: string }>; title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-line bg-white px-6 py-10 text-center">
      <Icon className="size-10 text-navy-600" aria-hidden />
      <p className="text-lg font-semibold text-navy-900">{title}</p>
      {body && <p className="max-w-md text-muted">{body}</p>}
      {action}
    </div>
  );
}

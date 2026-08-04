"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { Button, type ButtonProps } from "./button";

type CopyButtonProps = Omit<ButtonProps, "children" | "onClick"> & {
  value: string;
  label?: string;
  copiedLabel?: string;
  copyTitle?: string;
  iconClassName?: string;
};

export function CopyButton({
  value,
  label,
  copiedLabel = "Copied",
  copyTitle = "Copy",
  iconClassName,
  className,
  ...buttonProps
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<number | undefined>(undefined);

  useEffect(
    () => () => {
      if (resetTimer.current !== undefined) window.clearTimeout(resetTimer.current);
    },
    [],
  );

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      if (resetTimer.current !== undefined) window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Button
      {...buttonProps}
      className={cn(
        className,
        copied && "text-emerald-600 hover:text-emerald-700 dark:text-emerald-400",
      )}
      title={copied ? copiedLabel : copyTitle}
      aria-label={copied ? copiedLabel : copyTitle}
      onClick={() => void copy()}
    >
      {copied ? <Check className={iconClassName} /> : <Copy className={iconClassName} />}
      {label ? <span>{copied ? copiedLabel : label}</span> : null}
      {!label && copied ? <span className="sr-only">{copiedLabel}</span> : null}
    </Button>
  );
}

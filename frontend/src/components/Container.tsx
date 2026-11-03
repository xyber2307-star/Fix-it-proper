import type { ReactNode } from "react";

interface ContainerProps {
  children: ReactNode;
  className?: string;
}

export default function Container({ children, className = "" }: ContainerProps) {
  return <div className={`mx-auto w-full max-w-3xl px-4 sm:px-6 ${className}`}>{children}</div>;
}

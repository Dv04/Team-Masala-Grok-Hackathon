import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

const variants = {
  primary: "bg-indigo-500 text-white hover:bg-indigo-400",
  secondary: "bg-zinc-800 text-zinc-100 hover:bg-zinc-700",
  ghost: "bg-transparent text-zinc-300 hover:bg-zinc-800",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
}

export function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: PropsWithChildren<ButtonProps>) {
  return (
    <button
      className={`rounded-lg px-4 py-2 text-sm font-medium transition ${variants[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

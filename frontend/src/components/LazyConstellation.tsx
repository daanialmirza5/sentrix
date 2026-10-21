import { lazy, Suspense, type ComponentProps } from "react";

// three.js is ~550 kB; load it in its own chunk so the console shell renders immediately.
const Constellation3D = lazy(() => import("./Constellation3D"));

export default function LazyConstellation(props: ComponentProps<typeof Constellation3D>) {
  return (
    <Suspense fallback={<div style={{ height: props.height ?? 420 }} className="grid place-items-center">
      <div className="h-16 w-16 animate-pulse rounded-full bg-cyan-400/20 blur-md" /></div>}>
      <Constellation3D {...props} />
    </Suspense>
  );
}

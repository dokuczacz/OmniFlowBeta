import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { MVPShell } from "@/components/mvp-shell";

export default function MVPPage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <header className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-[0.2em]">
          OmniFlow MVP
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Operator Chat</h1>
        <p className="text-muted-foreground text-sm">
          Minimal layout built on the template styles. Backend wiring comes next.
        </p>
      </header>

      <MVPShell
        initialBackendUrl={process.env.OMNIFLOW_BACKEND_URL || ""}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Runs / Reports</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Runs history placeholder.
        </CardContent>
      </Card>
    </main>
  );
}

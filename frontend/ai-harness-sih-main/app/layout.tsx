import { Inter, Source_Sans_3 } from "next/font/google"
import { project } from "@/config/app-config.json"
import "./globals.css"
import { ThemeProvider } from "@/components/theme-provider"
import { WorkbenchProvider } from "@/lib/workbench-context"
import { SovereigntyMonitor } from "@/components/sovereignty/sovereignty-monitor"
import { AppSidebar } from "@/components/sidebar/app-sidebar"
import { ExecutionTimeline } from "@/components/timeline/execution-timeline"
import { cn } from "@/lib/utils"

const sourceSans3Heading = Source_Sans_3({ subsets: ["latin"], variable: "--font-heading" })
const inter = Inter({ subsets: ["latin"], variable: "--font-sans" })

export const metadata = {
  title: `${project.name} | ${project.tagline}`,
  description: project.description,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn("dark antialiased font-sans", inter.variable, sourceSans3Heading.variable)}
    >
      <body className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground text-sm font-normal">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <WorkbenchProvider>
            {/* Top Persistent Sovereignty Bar */}
            <SovereigntyMonitor />

            {/* Main Center Area: Left Sidebar + Page View */}
            <div className="flex flex-1 overflow-hidden">
              <AppSidebar />
              <main className="flex flex-1 overflow-hidden relative">
                {children}
              </main>
            </div>

            {/* Bottom Persistent Execution Timeline */}
            <ExecutionTimeline />
          </WorkbenchProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}

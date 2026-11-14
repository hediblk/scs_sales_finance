import { AppProvider, useApp } from "./state.jsx";
import { PAGES } from "./nav.js";
import { Sidebar, Topbar } from "./components/Shell.jsx";
import { EntityDrawer } from "./components/EntityDrawer.jsx";
import { ErrorBox, Loading } from "./components/ui.jsx";
import GapPage from "./pages/GapPage.jsx";
import QueuePage from "./pages/QueuePage.jsx";
import AskPage from "./pages/AskPage.jsx";
import DatasetPage from "./pages/DatasetPage.jsx";
import CleaningPage from "./pages/CleaningPage.jsx";
import WhatIfPage from "./pages/WhatIfPage.jsx";
import AccountsPage from "./pages/AccountsPage.jsx";

// Activity log is left out of the demo (file kept, not routed).
const PAGE_COMPONENTS = { dataset: DatasetPage, cleaning: CleaningPage, gap: GapPage, queue: QueuePage, whatif: WhatIfPage, accounts: AccountsPage, ask: AskPage };

function Shell() {
  const { meta, labels, error, retry, route, go } = useApp();
  const page = PAGES.find((p) => p.key === route.key) ?? PAGES[0];
  const Page = PAGE_COMPONENTS[page.page];

  return (
    <div className="app">
      <Sidebar pages={PAGES} active={page.key} onSelect={(k) => go(k)} />
      <main className="main">
        <Topbar page={page} labels={labels} />
        <div className="content">
          {error && <ErrorBox error={error} onRetry={retry} />}
          {!meta && !error ? <Loading what="Loading the data" /> : Page ? <Page key={page.key} params={route.params} /> : null}
        </div>
      </main>
      <EntityDrawer />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider pages={PAGES}>
      <Shell />
    </AppProvider>
  );
}

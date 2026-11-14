import { AppProvider, useApp } from "./state.jsx";
import { PAGES } from "./nav.js";
import { Sidebar, Topbar } from "./components/Shell.jsx";
import { EntityDrawer } from "./components/EntityDrawer.jsx";
import { ErrorBox, Loading } from "./components/ui.jsx";
import GapPage from "./pages/GapPage.jsx";
import QueuePage from "./pages/QueuePage.jsx";
import AccountsPage from "./pages/AccountsPage.jsx";
import LogPage from "./pages/LogPage.jsx";
import AskPage from "./pages/AskPage.jsx";
import DatasetPage from "./pages/DatasetPage.jsx";

const PAGE_COMPONENTS = { dataset: DatasetPage, gap: GapPage, queue: QueuePage, accounts: AccountsPage, log: LogPage, ask: AskPage };

function Shell() {
  const { meta, labels, error, route, go } = useApp();
  const page = PAGES.find((p) => p.key === route.key) ?? PAGES[0];
  const Page = PAGE_COMPONENTS[page.page];

  return (
    <div className="app">
      <Sidebar pages={PAGES} active={page.key} onSelect={(k) => go(k)} />
      <main className="main">
        <Topbar page={page} labels={labels} />
        <div className="content">
          {error && <ErrorBox error={error} />}
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

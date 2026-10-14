import { fr } from "@/i18n/fr";

import { Empty, PageHead } from "./common";
import { Link } from "./Link";

export function NotFound() {
  return (
    <div className="page">
      <PageHead title={fr.nav.notFoundTitle} />
      <Empty title={fr.nav.notFound}>
        <Link to={{ page: "instances" }}>{fr.nav.instances}</Link>
      </Empty>
    </div>
  );
}

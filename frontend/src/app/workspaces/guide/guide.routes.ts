import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { from } from 'rxjs';

import { onEvents, routeData } from '../../routing/route-metadata';
import { startRoute } from '../../routing/route-resolver';
import { GuideStore } from '../../stores/guide.store';

/** One store for every chapter URL, so moving between chapters keeps the
 *  index and the bodies already fetched. No server event refreshes the
 *  guide: chapters change only with a deploy. */
export const guideRoutes: Routes = [{
  path: '',
  providers: [GuideStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Guide', onEvents()),
  resolve: { ready: startRoute(() => from(inject(GuideStore).ensureLoaded())) },
  children: [
    { path: '', loadComponent: () => import('./guide').then((m) => m.Guide) },
    { path: ':slug', loadComponent: () => import('./guide').then((m) => m.Guide) },
  ],
}];

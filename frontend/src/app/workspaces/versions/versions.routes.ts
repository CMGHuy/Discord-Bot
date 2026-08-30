import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { VersionsStore } from '../../stores/versions.store';
export const versionsRoutes: Routes = [{ path: '', providers: [VersionsStore], runGuardsAndResolvers: 'always', data: routeData('Versions', onEvents('bot')), resolve: { ready: resolveRoute(() => inject(VersionsStore).resolve()) }, loadComponent: () => import('./versions').then((m) => m.Versions) }];
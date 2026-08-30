import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { RiskStore } from '../../stores/risk.store';
export const riskRoutes: Routes = [{ path: '', providers: [RiskStore], runGuardsAndResolvers: 'always', data: routeData('Risk', onEvents('risk', 'trades')), resolve: { ready: resolveRoute(() => inject(RiskStore).resolve()) }, loadComponent: () => import('./risk').then((m) => m.Risk) }];
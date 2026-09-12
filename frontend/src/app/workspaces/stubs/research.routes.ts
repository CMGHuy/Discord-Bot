import { Routes } from '@angular/router';
export const researchRoutes: Routes = [{ path: '', data: { planned: 'A symbol research desk', insteadLabel: 'Ticker detail', insteadLink: '/watchlist' }, loadComponent: () => import('./planned-workspace').then((m) => m.PlannedWorkspace) }];

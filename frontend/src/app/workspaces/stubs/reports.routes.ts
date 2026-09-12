import { Routes } from '@angular/router';
export const reportsRoutes: Routes = [{ path: '', data: { planned: 'Scheduled trading reports and exports', insteadLabel: 'Analytics', insteadLink: '/analytics' }, loadComponent: () => import('./planned-workspace').then((m) => m.PlannedWorkspace) }];

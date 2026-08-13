/* One error type for the whole application.
 *
 * Every failure that comes out of `ApiClient` is an `ApiError` -- a 401, a
 * 500, a dead server, a proxy returning HTML, a browser offline. Callers get
 * one `catch` shape and one field to branch on, and never have to ask
 * whether they are holding an `HttpErrorResponse`, a `ProgressEvent` or a
 * `TypeError` from the fetch layer.
 */

/** The stable codes the v1 API emits. `unavailable` is also what the client
 *  synthesises when the server did not speak the protocol at all. */
export type ApiErrorCode =
  | 'auth'
  | 'not_found'
  | 'invalid'
  | 'conflict'
  | 'unavailable';

export class ApiError extends Error {
  constructor(
    readonly code: ApiErrorCode | string,
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** True when the failure means "not logged in", whatever produced it. */
  get isAuth(): boolean {
    return this.code === 'auth' || this.status === 401;
  }
}

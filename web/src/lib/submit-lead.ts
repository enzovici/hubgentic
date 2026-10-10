// The one place that decides where the contact form goes.
// Today: Netlify Forms (the form is detected in the built HTML by its
// data-netlify attribute and name="pmi-contatti").
// To switch provider, change FORM_ENDPOINT and, if needed, the body format below.
export const FORM_ENDPOINT = '/';

export async function submitLead(form: HTMLFormElement): Promise<void> {
  const body = new URLSearchParams();
  for (const [key, value] of new FormData(form)) {
    if (typeof value === 'string') body.append(key, value);
  }
  const res = await fetch(FORM_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!res.ok) throw new Error(`Form endpoint answered ${res.status}`);
}

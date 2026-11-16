# What AAC Editor's results mean

Every edit AAC Editor makes to TD Snap, Grid 3 or an exported file ends in exactly one of the results below. The message on screen always says which one, what changed, whether your original is safe, what to do next, and whether it is safe to try again. Each message also shows a short **reference** (for example `a3f9`); quote it if you ask for help, and choose **Copy a support report** at the bottom of the window.

| What you see | What it means | What to do | Safe to try again? |
|---|---|---|---|
| **Done** | The edit was made and every button it touched was checked afterwards. | Nothing. | Not needed. |
| **Done, with notes** | The words, messages and positions were made and checked. Some extras (symbols, topic border colours) could not be applied or checked automatically, and the notes name them. | Look at the named buttons and add the symbol or colour in the AAC app if you want it. | Not needed. |
| **The edit was not started** | Something was not ready, so AAC Editor changed nothing. The message says what (for example TD Snap was in edit mode, a message box was open, another window was in front, or the page changed since you reviewed it). | Fix what the message says, then review the edit again. | Yes. |
| **The edit did not go through, and the page was put back** | AAC Editor started the edit, something went wrong, and it undid its own changes. It then checked the page matches how it was before. | Review the edit again and retry. | Yes, after reviewing again. |
| **The edit did not finish, and the page may be partly changed** | AAC Editor started the edit and could not fully undo it. The page is readable but differs from how it was. | Look at the page in the AAC app, compare it with what you reviewed, and fix it by hand or with the app's own Undo. | **Not until you have checked the page.** |
| **The edit stopped part-way. Check the page** | AAC Editor could not tell what is on the page now (the AAC app stopped responding, closed, or showed an unexpected message). | Look at the page in the AAC app before doing anything else. If the app stopped responding, AAC Editor pauses live editing until you choose **Change app** and connect again. | **Not until you have checked the page.** |
| **The edit went through, but its answer was lost** | The edit finished, but the connection to AAC Editor dropped before the result arrived. AAC Editor asked afterwards and was told it succeeded. | Look at the page to see it. | **No: do not apply it again.** |

## Banners you may see when AAC Editor starts

- **An edit was interrupted before it finished.** AAC Editor was closed, crashed, or was stopped while it was changing a page in the AAC app. Look at the page you were editing before making another edit, then choose **I have checked the page**.
- **An edited copy of a file was never saved.** You quit while an exported file had edits you had not saved. AAC Editor kept them. Choose **Open it** to carry on and save, or **Discard it**. The original file was never changed either way.
- **AAC Editor restarted.** The page in your browser belongs to a copy of the app that has stopped. Reload it. Anything you had reviewed but not applied needs reviewing again.

## Batches of pages

When you apply several queued pages, each page has its own result. The run stops at the first page that is anything other than **Done** or **not started**, and the pages after it are listed as **Not attempted**. Only the last page that was applied can be undone with **Undo my last change**.

## Before editing a client's system

- Take a backup in TD Snap or Grid 3 first. For Grid 3, AAC Editor also keeps a copy of the grid set from just before each edit, in the `backups` folder shown under **What AAC Editor saves**.
- For large changes, edit an exported file and import it back; it has the strongest guarantees.
- Keep the AAC app in front, and do not use the mouse or keyboard while an edit runs.
- Live editing cannot be made fully transactional, because TD Snap and Grid 3 offer no way to do that. AAC Editor's promise is narrower and exact: **after any live edit it will tell you truthfully whether the page is changed, unchanged, or needs checking, and it will never continue to another page unless the last one was checked.**

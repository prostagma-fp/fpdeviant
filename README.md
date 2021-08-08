# fpdeviant

Script to create DeviantArt curations. Should eventually be merged into fpcurator.

1. Register a [DeviantArt application](https://www.deviantart.com/developers/) with your account
2. Insert your app's client_id and client_secret in `deviantart.txt`. This is like your account password; do not share it
3. `pip install deviantart`
4. Run `fpdeviant.py`

Supports individual urls or batches (drag bacth files into the console); will look into a deviant's submissions if you input a user's url, but Scraps must be parsed individually.


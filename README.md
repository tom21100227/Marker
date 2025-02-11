# Marker

A small python tool I wrote to label videos for experiment videos. Given an video file, you can labelled it as 0 - Negative, 1 - Questionable, and 2 - Positive. With some small tweaks you can use it to label as many state as you wish. 

## Usage

- `[0,1,2]`: Press to label current frame as one of the 3 states, hold to play the video while labelling all viewed frames as such state.
- `space`: play the video without labelling.
- `left/right arrow key`: go back/forward 1 frame
- `[<,>]`: fast forward / rewind 5 seconds of video
- `q`: quit. 

There's two progress bar in the bottom of the interface: 
- top being an overview: from the start frame to the end frame, grey - not labelled yet, red/yellow/green = neg/question/positive.
- bottom being a finer resolution one, showing states of the +/- 5 seconds frames that you're currently viewing.

Once you lablled all frames / hit quit, a review video would generate with the overview progress bar and a cursor so you can visually review the corresponding states. 

Labelled results are stored in a CSV with 3 columns: frame #, state #, and state alias. In the uploaded version for my experiment, alias are `"not flying", "transition", and "flying"`. 

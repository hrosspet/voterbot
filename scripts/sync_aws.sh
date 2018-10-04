#AWS_HOST=ec2-54-191-17-146.us-west-2.compute.amazonaws.com
#AWS_HOST=ec2-54-213-240-113.us-west-2.compute.amazonaws.com
AWS_HOST=ec2-54-187-239-29.us-west-2.compute.amazonaws.com
#FOLDER=training_2017_12_15
FOLDER=training_2018_01_04
rsync -avzh -e "ssh -i ~/siw/prg/steem1.pem" ec2-user@$AWS_HOST:~/steem_ailib/model_weights_* ~/steem_ailib/$FOLDER/
rsync -avzh -e "ssh -i ~/siw/prg/steem1.pem" ec2-user@$AWS_HOST:~/steem_ailib/data/plot_data.npz ~/steem_ailib/$FOLDER/
rsync -avzh -e "ssh -i ~/siw/prg/steem1.pem" ec2-user@$AWS_HOST:~/steem_ailib/$FOLDER/training.txt ~/steem_ailib/$FOLDER/

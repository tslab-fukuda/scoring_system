new Vue({
    el: '#final-grading-form',
    data: {
        showScore: false
    },
    methods: {
        toggleScore() { this.showScore = !this.showScore; }
    }
});
